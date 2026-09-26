"""What an iSWAP transport plan sweeps through, and what it would hit.

`check_plan(transport, plan)` follows a plan's steps through the arm's joints and turns each into
the moves of the rigid parts that make it: the column (the iSWAP head) shifts with the elbow; link 1
turns about the elbow and shifts with it; the gripper and anything held turn about the wrist and
shift with it; the fingers do too, slid along the jaws by however far they stand open. The rest of
the X-arm - the channels, the 96-head - shifts with X.

Two checks come of it:

- against everything that stands still around the arm (the deck, the machine), with the X-arm's
  travel spanned whole at every moment, since X runs while Y and the joints move;
- against the channels and the 96-head, in the X-arm's own frame, where X moves nothing.

What a plan means to touch is never reported: what is picked up and what it stands on, what it is
put down on and what that stands on.

Turns are cut finely enough that no point strays more than `TURN_SLACK` from the hulls taken
(`Kinematics.arcs`): the hull of a piece at both ends of an arc holds every chord, and a point's way
strays from its chord by no more than its curvature allows.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Dict, List, Optional, Sequence, Tuple

from pylabrobot.hamilton.star.driver.features.iswap_transport import (
  Grip,
  Open,
  Plan,
  Release,
  Rise,
  Travel,
  iSWAPTransport,
)
from pylabrobot.resources.collision import (
  Collision,
  Group,
  Obstacles,
  Pose,
  Segment,
  check,
  solid_pieces,
)
from pylabrobot.resources.resource import Resource

# Resources that are enclosures, not solids: the X-arm travels into the left extension housing, and
# the model has the 96-head inside it whenever the arm is far enough left.
ENCLOSURES = ("left_extension_housing",)
# The most any point of the arm may stray from the hulls a turn is checked with, in mm.
TURN_SLACK = 0.5
# How far past the grip centre anything the gripper carries reaches, at most, in mm: the fingers
# and a plate's half-diagonal. Only bounds how finely turns are cut.
CARRIED_REACH = 150.0


@dataclasses.dataclass(frozen=True)
class Joints:
  """Where the arm's drives are: the elbow's X and Y and the grip centre's Z, in mm on the deck, and
  the two joints' drive angles, in degrees."""

  x: float
  y: float
  z: float
  elbow: float
  wrist: float

  def but(self, **changes: float) -> "Joints":
    return dataclasses.replace(self, **changes)


@dataclasses.dataclass
class Parts:
  """The arm's rigid parts, and the X-arm they ride."""

  column: Resource
  link: Resource
  gripper: Resource
  fingers: Tuple[Resource, Resource]
  arm: Resource


def parts_of(transport: iSWAPTransport) -> Parts:
  gripper = transport.iswap.gripper
  link = gripper.parent
  column = link.parent
  arm = column.parent
  left, right = gripper.fingers
  return Parts(column, link, gripper, (left, right), arm)


def joints_now(transport: iSWAPTransport) -> Joints:
  iswap = transport.iswap
  drive = iswap.elbow_get_reference_point_location()
  elbow, wrist = iswap.elbow_drive_get_angle(), iswap.wrist_drive_get_angle()
  if drive is None or elbow is None or wrist is None:
    raise RuntimeError("the iSWAP is not modelled, so what it sweeps is not known")
  return Joints(drive.x, drive.y, transport._grip_z_now(), elbow, wrist)


class Kinematics:
  """Where the parts go, as rigid moves from where they are at `now`, for any joints."""

  def __init__(self, transport: iSWAPTransport, now: Joints):
    self.link_1, self.tool, self.straight = transport._lengths()
    self.now = now
    self.origin = transport.deck.get_absolute_location()  # the checks are made in absolute terms
    turned = math.radians(transport.iswap.gripper.get_absolute_rotation().z)
    self.jaw_axis = (-math.sin(turned), math.cos(turned))  # the gripper's own +Y, now

  def wrist(self, j: Joints) -> Tuple[float, float]:
    link = math.radians(j.elbow - 90.0)
    return j.x + self.link_1 * math.cos(link), j.y + self.link_1 * math.sin(link)

  def _abs(self, x: float, y: float) -> Tuple[float, float, float]:
    return (x + self.origin.x, y + self.origin.y, 0.0)

  def column(self, j: Joints) -> Pose:
    return Pose(shift=(j.x - self.now.x, j.y - self.now.y, j.z - self.now.z))

  def link(self, j: Joints) -> Pose:
    return Pose(j.elbow - self.now.elbow, self._abs(self.now.x, self.now.y), self.column(j).shift)

  def gripper(self, j: Joints) -> Pose:
    w0, w = self.wrist(self.now), self.wrist(j)
    turn = (j.elbow - self.now.elbow) + (j.wrist - self.now.wrist)
    return Pose(turn, self._abs(*w0), (w[0] - w0[0], w[1] - w0[1], j.z - self.now.z))

  def finger(self, j: Joints, side: float, opened: float) -> Pose:
    """A finger, slid out by half of `opened` - how much wider the jaws are than now - on its side."""
    slide = side * opened / 2.0
    return self.gripper(j).after(self.jaw_axis[0] * slide, self.jaw_axis[1] * slide)

  def arcs(self, a: Joints, b: Joints) -> Tuple[int, float]:
    """How many arcs a turn from `a` to `b` is cut into, and how far from the hulls a point strays.

    A point the gripper carries is at E + R(e) a + R(e + w) b - the elbow, link 1 turned by the
    elbow, and the point's place from the wrist turned by both - so over an arc of turns de and dw
    its second derivative is at most de^2 |a| + (de + dw)^2 |b|, and a point of link 1 at most
    de^2 of its distance from the elbow. A curve strays from its chord by at most an eighth of its
    second derivative's bound.
    """
    de, dw = math.radians(abs(b.elbow - a.elbow)), math.radians(abs(b.wrist - a.wrist))
    carried = self.tool + CARRIED_REACH
    bend = max(
      de * de * (self.link_1 + CARRIED_REACH), de * de * self.link_1 + (de + dw) ** 2 * carried
    )
    if bend == 0:
      return 1, 0.0
    n = max(1, math.ceil(math.sqrt(bend / (8 * TURN_SLACK))))
    return n, bend / (n * n) / 8


SIDES = (1.0, -1.0)  # the fingers' sides of the jaws, as the gripper model orders them


class _Sweeps:
  """The segments each part sweeps, a plan step taking one unit of time."""

  def __init__(self, kin: Kinematics, fixed_x: bool):
    self.kin = kin
    self.fixed_x = fixed_x
    self.opened = 0.0
    # While something is held: how it was put on the gripper - undoing the gripper's move up to
    # the grip, so that it rides the gripper's moves from there on.
    self.held_since: Optional[Pose] = None
    self.parts: Dict[str, List[Segment]] = {
      "held": [],
      "column": [],
      "link": [],
      "gripper": [],
      "finger 0": [],
      "finger 1": [],
    }
    self.arm: List[Segment] = []

  def _states(self, a: Joints, b: Joints, xs: List[float], f0: float, f1: float) -> List[Joints]:
    def at(f: float, x: float) -> Joints:
      return Joints(
        self.kin.now.x if self.fixed_x else x,
        a.y + (b.y - a.y) * f,
        a.z + (b.z - a.z) * f,
        a.elbow + (b.elbow - a.elbow) * f,
        a.wrist + (b.wrist - a.wrist) * f,
      )

    return [at(f, x) for x in xs for f in (f0, f1)]

  def _add(self, states: List[Joints], slack: float, s0: float, s1: float, opens=(0.0, 0.0)):
    kin = self.kin
    for name, pose in (("column", kin.column), ("link", kin.link), ("gripper", kin.gripper)):
      self.parts[name].append(Segment([pose(s) for s in states], slack, s0, s1))
    for k, side in enumerate(SIDES):
      poses = [kin.finger(s, side, self.opened + o) for s in states for o in set(opens)]
      self.parts[f"finger {k}"].append(Segment(poses, slack, s0, s1))
    if self.held_since is not None:
      fix = self.held_since
      poses = [fix.then(kin.gripper(s)) for s in states]
      self.parts["held"].append(Segment(poses, slack, s0, s1))

  def move(self, a: Joints, b: Joints, x_span: Tuple[float, float], t0: float, t1: float) -> None:
    """From `a` to `b` - the joints on a straight line in joint space - with X anywhere in
    `x_span` all the while. A move with no turn in it is a box on independent axes: exact."""
    xs = sorted({x_span[0], x_span[1]})
    n, slack = self.kin.arcs(a, b)
    if slack == 0:
      corners = [a.but(y=y, z=z) for y in {a.y, b.y} for z in {a.z, b.z}]
      states = [s for c in corners for s in self._states(c, c, xs, 0.0, 0.0)]
      self._add(states, 0.0, t0, t1)
      return
    for k in range(n):
      states = self._states(a, b, xs, k / n, (k + 1) / n)
      self._add(states, slack, t0 + (t1 - t0) * k / n, t0 + (t1 - t0) * (k + 1) / n)

  def jaws(self, at: Joints, change: float, t0: float) -> None:
    """The fingers sliding apart by `change`, at `at`."""
    self._add(self._states(at, at, [at.x], 0.0, 0.0), 0.0, t0, t0 + 1, (0.0, change))
    self.opened += change


@dataclasses.dataclass
class PlanSweeps:
  """What each part of the arm sweeps over a plan, and what the plan means to touch."""

  groups: List[Group]
  arm: Optional[Group]
  touches: List[Resource]
  end: Joints


def _standing_on(resource: Resource, stop: Resource) -> List[Resource]:
  """`resource` and what it stands on, up to but not including `stop`."""
  out = []
  r: Optional[Resource] = resource
  while r is not None and r is not stop:
    out.append(r)
    r = r.parent
  return out


def sweeps(transport: iSWAPTransport, plan: Plan, fixed_x: bool = False) -> PlanSweeps:
  """Follow `plan` from where the arm is now, as `iSWAPTransport.execute` runs it."""
  parts = parts_of(transport)
  now = joints_now(transport)
  sw = _Sweeps(Kinematics(transport, now), fixed_x)
  width = float(getattr(transport.iswap.gripper, "jaw_width", 0.0) or 0.0)
  held: Optional[Resource] = transport.holding
  if held is not None:
    sw.held_since = Pose()
  deck = transport.deck
  touches: List[Resource] = []
  j = now
  for t, step in enumerate(plan.steps):
    if isinstance(step, Rise):
      b = j.but(z=step.z)
      sw.move(j, b, (j.x, j.x), t, t + 1)
      j = b
    elif isinstance(step, Travel):
      target = Joints(step.elbow_x, step.elbow_y, j.z, step.elbow_angle, step.wrist_angle)
      start, end = j, target.but(x=j.x)  # X is spanned whole; the legs are Y and the turn
      turned = start.but(elbow=end.elbow, wrist=end.wrist)
      if step.order == "translate_first":
        legs = [(start, start.but(y=end.y)), (start.but(y=end.y), end)]
      elif step.order == "turn_first":
        legs = [(start, turned), (turned, end)]
      else:
        at = start.but(y=step.turn_y if step.turn_y is not None else start.y)
        there = at.but(elbow=end.elbow, wrist=end.wrist)
        legs = [(start, at), (at, there), (there, end)]
      for k, (a, b) in enumerate(legs):
        sw.move(a, b, (j.x, step.elbow_x), t + k / len(legs), t + (k + 1) / len(legs))
      sw.arm.append(Segment([Pose(), Pose(shift=(step.elbow_x - j.x, 0.0, 0.0))], 0.0, t, t + 1))
      j = target
    elif isinstance(step, (Open, Release)):
      if step.width > width:
        sw.jaws(j, step.width - width, t)
      else:
        sw.opened += step.width - width
      width = step.width
      if isinstance(step, Release):
        sw.held_since = None
        touches += [step.resource, *step.resource.get_all_children()]
        if isinstance(step.destination, Resource):
          touches += _standing_on(step.destination, deck)
    elif isinstance(step, Grip):
      sw.opened += step.width - width  # closing on it: towards what they are meant to touch
      width = step.width
      held = step.resource
      sw.held_since = sw.kin.gripper(j).inverse()
      touches += [step.resource, *step.resource.get_all_children()]
      if step.resource.parent is not None:
        touches += _standing_on(step.resource.parent, deck)

  riders = [c for c in parts.gripper.children if c is transport.holding]

  def pieces(root: Resource, *leave_out: Resource):
    return solid_pieces(root, {id(r) for r in leave_out})

  groups = [
    Group("iSWAP column", pieces(parts.column, parts.link), sw.parts["column"]),
    Group("iSWAP link 1", pieces(parts.link, parts.gripper), sw.parts["link"]),
    Group("iSWAP gripper", pieces(parts.gripper, *parts.fingers, *riders), sw.parts["gripper"]),
  ]
  if held is not None:
    groups.append(Group(held.name, pieces(held), sw.parts["held"]))
  for k, finger in enumerate(parts.fingers):
    groups.append(Group(f"iSWAP {finger.name}", pieces(finger), sw.parts[f"finger {k}"]))
  arm = Group("X-arm", pieces(parts.arm, parts.column), sw.arm) if sw.arm else None
  return PlanSweeps(groups, arm, touches, j)


def check_plan(
  transport: iSWAPTransport, plan: Plan, clearance: float = 0.0, root: Optional[Resource] = None
) -> List[Collision]:
  """Everything `plan` would bring the arm, what it holds, or what rides the X-arm with it, within
  `clearance` mm of.

  Args:
    transport: the transport the plan is for, with the arm where the plan starts.
    plan: from `plan_pick_up` or `plan_drop`.
    clearance: how close is too close, in mm. 0 reports only what meets.
    root: what stands around the arm; the whole tree the deck is in when None.
  """
  parts = parts_of(transport)
  if root is None:
    root = transport.deck
    while root.parent is not None:
      root = root.parent
  around = sweeps(transport, plan)
  moving = around.groups + ([around.arm] if around.arm else [])
  standing = Obstacles(solid_pieces(root, {id(parts.arm)}, ENCLOSURES))
  found = check(root, moving, clearance, around.touches, standing, between_groups=False)
  # Against the channels and the 96-head, which ride the same X-arm: in its frame.
  in_arm = sweeps(transport, plan, fixed_x=True)
  riding = Obstacles(solid_pieces(parts.arm, {id(parts.column)}))
  found += check(parts.arm, in_arm.groups, clearance, in_arm.touches, riding, between_groups=False)
  return found


def describe(collisions: Sequence[Collision]) -> str:
  return "\n".join(str(c) for c in collisions) or "nothing in the way"
