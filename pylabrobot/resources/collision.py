"""Collision checks of motions against a resource tree: what moves, swept, against what stands still.

A motion is checked without checking everything against everything. What moves is known - the
groups a command moves, each rigid - so each group's solid pieces are swept along its way, and only
the pieces standing still that a sweep's bounding box meets, found in a bounding-volume tree, are
tested exactly. Two groups moving at once are tested against each other only over the same slice of
time.

Solids. Every resource is a box - its size, where it is and how it is turned - and it is taken to
be solid or not by how it holds its children:

- a resource with no children is solid, unless it is flat (a site, a trash's opening);
- a plate, a tip rack, any itemized resource, is solid as a whole: its items are inside it, but what
  sits in its items - a tip in a tip spot - is looked at too;
- a resource whose children lie outside its box - a channel with its tip mounting shaft below it, a
  finger with its pad - is solid, and so are its children;
- a resource whose children lie inside its box - a deck, a carrier, the X-arm - is a frame: only
  its base, from its bottom up to the lowest thing it holds, is solid (a carrier's body under its
  sites, the deck's slab), and its children are looked at in turn.

Sweeps. A group's way is cut into segments; each segment is the convex hull of the group's pieces
at a few poses, grown by a slack. The hull is exact for a straight move (its two ends) and for moves
on independent axes (the corners of the box they span); a turn is cut into short arcs, each grown
by the most any point strays from the chord - `turn_slack`.

The exact test is GJK: the distance between two convex hulls, each grown by a radius. Things are in
collision when closer than the clearance asked for; things that touch - a plate resting on its site
- are not, by `CONTACT` of slack.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from pylabrobot.resources.coordinate import Coordinate
from pylabrobot.resources.itemized_resource import ItemizedResource
from pylabrobot.resources.resource import Resource

Vec = Tuple[float, float, float]

# How far two things may overlap and still only touch, in mm: a plate resting on a site, a finger on
# the side of what it grips. Every solid is drawn in by this much on each face, so things that touch
# stay a little apart and only things that go into each other meet.
CONTACT = 0.05


# -- vectors -------------------------------------------------------------------------------------


def _sub(a: Vec, b: Vec) -> Vec:
  return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a: Vec, b: Vec) -> Vec:
  return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _dot(a: Vec, b: Vec) -> float:
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _scale(a: Vec, k: float) -> Vec:
  return (a[0] * k, a[1] * k, a[2] * k)


def _vec(c: Coordinate) -> Vec:
  return (c.x, c.y, c.z)


# -- poses ---------------------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Pose:
  """A rigid move: a turn of `turn` degrees about the vertical through `pivot`, then a shift."""

  turn: float = 0.0
  pivot: Vec = (0.0, 0.0, 0.0)
  shift: Vec = (0.0, 0.0, 0.0)

  def apply(self, p: Vec) -> Vec:
    if self.turn:
      c, s = math.cos(math.radians(self.turn)), math.sin(math.radians(self.turn))
      x, y = p[0] - self.pivot[0], p[1] - self.pivot[1]
      p = (self.pivot[0] + c * x - s * y, self.pivot[1] + s * x + c * y, p[2])
    return _add(p, self.shift)

  def _linear(self) -> Tuple[float, Vec]:
    """This pose as a turn about the origin and a shift: p -> R p + t."""
    moved = self.apply((0.0, 0.0, 0.0))
    return self.turn, moved

  def then(self, other: "Pose") -> "Pose":
    """This pose, followed by `other`."""
    turn, t = self._linear()
    return Pose(turn + other.turn, (0.0, 0.0, 0.0), other.apply(t))

  def inverse(self) -> "Pose":
    turn, t = self._linear()
    back = Pose(-turn)
    return Pose(-turn, (0.0, 0.0, 0.0), _scale(back.apply(t), -1.0))

  def after(self, x: float, y: float, z: float = 0.0) -> "Pose":
    """This pose, taken after a shift by (`x`, `y`, `z`) where things are now."""
    d = (x, y, z)
    return Pose(self.turn, _sub(self.pivot, d), _add(self.shift, d))

  @staticmethod
  def shifted(x: float = 0.0, y: float = 0.0, z: float = 0.0) -> "Pose":
    return Pose(shift=(x, y, z))


STILL = Pose()


# -- solid pieces --------------------------------------------------------------------------------


@dataclasses.dataclass
class Piece:
  """One convex solid: the corners of a box, and the resource it stands for."""

  resource: Resource
  points: List[Vec]

  def __post_init__(self) -> None:
    self.lo, self.hi = _bounds(self.points)


def _bounds(points: Iterable[Vec]) -> Tuple[Vec, Vec]:
  xs, ys, zs = zip(*points)
  return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def _corners(
  resource: Resource, z_from: float = 0.0, z_to: Optional[float] = None, inset: float = 0.0
) -> List[Vec]:
  """The eight corners of `resource`'s box - or of the slab of it from `z_from` to `z_to` above its
  bottom - absolute, each face moved in by `inset`."""
  origin = _absolute(resource)
  rotation = resource.get_absolute_rotation()
  sx, sy, sz = resource.get_size_x(), resource.get_size_y(), resource.get_size_z()
  top = sz if z_to is None else z_to

  def span(a: float, b: float) -> Tuple[float, float]:
    return (a + inset, b - inset) if b - a > 2 * inset else ((a + b) / 2, (a + b) / 2)

  return [
    _vec(origin + Coordinate(x, y, z).rotated(rotation))
    for x in span(0.0, sx)
    for y in span(0.0, sy)
    for z in span(z_from, top)
  ]


def _absolute(resource: Resource) -> Coordinate:
  """Where `resource` is: absolute, or - in a tree whose root has not been put anywhere - in the
  root's own terms."""
  top = resource
  while top.parent is not None:
    top = top.parent
  if top.location is not None:
    return resource.get_absolute_location()
  return Coordinate.zero() if resource is top else resource.get_location_wrt(top)


def _flat(resource: Resource) -> bool:
  return min(resource.get_size_x(), resource.get_size_y(), resource.get_size_z()) <= CONTACT


def solid_pieces(
  root: Resource, leave_out: Optional[Set[int]] = None, hollow: Iterable[str] = ()
) -> List[Piece]:
  """Every solid piece under `root` (itself included), as the module docstring sets out, less
  anything in `leave_out` (resource ids) and what is under it.

  Args:
    hollow: categories of resource that are enclosures - a housing something travels into - and
      so not solid themselves, whatever their children.
  """
  leave_out = leave_out or set()
  enclosures = set(hollow)
  pieces: List[Piece] = []
  boxes: Dict[int, Tuple[Vec, Vec]] = {}
  lows: Dict[int, Optional[float]] = {}

  def box(resource: Resource) -> Tuple[Vec, Vec]:
    if id(resource) not in boxes:
      boxes[id(resource)] = _bounds(_corners(resource))
    return boxes[id(resource)]

  def inside(child: Resource, parent: Resource) -> bool:
    """Whether `child` is held within `parent`'s box - its centre is - rather than hung on it."""
    (c_lo, c_hi), (p_lo, p_hi) = box(child), box(parent)
    return all(p_lo[k] - CONTACT <= (c_lo[k] + c_hi[k]) / 2 <= p_hi[k] + CONTACT for k in range(3))

  def lowest(resource: Resource) -> Optional[float]:
    """The lowest bottom of anything `resource` holds, left out things aside."""
    if id(resource) in lows:
      return lows[id(resource)]
    low: Optional[float] = None
    for child in resource.children:
      if id(child) in leave_out:
        continue
      if not _flat(child) or not child.children:
        z = box(child)[0][2]
        low = z if low is None else min(low, z)
      below = lowest(child)
      if below is not None:
        low = below if low is None else min(low, below)
    lows[id(resource)] = low
    return low

  def visit(resource: Resource) -> None:
    if id(resource) in leave_out:
      return
    children = [c for c in resource.children if id(c) not in leave_out]
    if resource.category in enclosures:
      for child in children:
        visit(child)
      return
    if isinstance(resource, ItemizedResource):
      if not _flat(resource):
        pieces.append(Piece(resource, _corners(resource, inset=CONTACT)))
      for item in children:
        for held in item.children:
          visit(held)
      return
    if not children:
      if not _flat(resource):
        pieces.append(Piece(resource, _corners(resource, inset=CONTACT)))
      return
    if _flat(resource):
      pass
    elif any(inside(c, resource) for c in children):
      low = lowest(resource)
      base = (low - box(resource)[0][2]) if low is not None else resource.get_size_z()
      if base > 2 * CONTACT:
        top = min(base, resource.get_size_z())
        pieces.append(Piece(resource, _corners(resource, 0.0, top, CONTACT)))
    else:
      pieces.append(Piece(resource, _corners(resource, inset=CONTACT)))
    for child in children:
      visit(child)

  visit(root)
  return pieces


# -- the exact test: GJK distance ----------------------------------------------------------------


def _support(points: Sequence[Vec], d: Vec) -> Vec:
  best, best_dot = points[0], _dot(points[0], d)
  for p in points[1:]:
    k = _dot(p, d)
    if k > best_dot:
      best, best_dot = p, k
  return best


def _solve(g: List[List[float]], b: List[float]) -> Optional[List[float]]:
  n = len(b)
  m = [row[:] + [b[i]] for i, row in enumerate(g)]
  for col in range(n):
    pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
    if abs(m[pivot][col]) < 1e-12:
      return None
    m[col], m[pivot] = m[pivot], m[col]
    for r in range(n):
      if r != col:
        f = m[r][col] / m[col][col]
        for c in range(col, n + 1):
          m[r][c] -= f * m[col][c]
  return [m[i][n] / m[i][i] for i in range(n)]


def _closest_on_simplex(simplex: List[Vec]) -> Tuple[Vec, List[Vec]]:
  """The point of the simplex's hull nearest the origin, and the smallest face it lies on."""
  best: Optional[Tuple[float, Vec, List[Vec]]] = None
  n = len(simplex)
  for mask in range(1, 1 << n):
    face = [simplex[i] for i in range(n) if mask >> i & 1]
    p0 = face[0]
    edges = [_sub(p, p0) for p in face[1:]]
    if edges:
      mu = _solve([[_dot(a, b) for b in edges] for a in edges], [-_dot(a, p0) for a in edges])
      if mu is None or any(m < -1e-12 for m in mu) or sum(mu) > 1 + 1e-12:
        continue
      point = p0
      for m, e in zip(mu, edges):
        point = _add(point, _scale(e, m))
    else:
      point = p0
    d2 = _dot(point, point)
    if (
      best is None
      or d2 < best[0] - 1e-15
      or (abs(d2 - best[0]) <= 1e-15 and len(face) < len(best[2]))
    ):
      best = (d2, point, face)
  assert best is not None
  return best[1], best[2]


def distance(a: Sequence[Vec], b: Sequence[Vec], stop_beyond: float = math.inf) -> float:
  """The distance between the convex hulls of two point sets; 0 if they meet. Stops early, with a
  lower bound, once the hulls are sure to be further apart than `stop_beyond`."""
  v = _sub(a[0], b[0])
  simplex: List[Vec] = []
  for _ in range(64):
    vv = _dot(v, v)
    if vv < 1e-18:
      return 0.0
    w = _sub(_support(a, _scale(v, -1.0)), _support(b, v))
    vw = _dot(v, w)
    if vw > 0 and vw * vw > stop_beyond * stop_beyond * vv:
      return vw / math.sqrt(vv)  # a separating plane further than asked for
    if vv - vw <= 1e-9 * max(vv, 1.0):
      return math.sqrt(vv)
    simplex.append(w)
    v, simplex = _closest_on_simplex(simplex)
    if len(simplex) == 4:
      return 0.0
  return math.sqrt(_dot(v, v))


# -- the bounding-volume tree --------------------------------------------------------------------


class _Node:
  __slots__ = ("lo", "hi", "left", "right", "pieces")

  def __init__(self, pieces: List[Piece]):
    self.lo, self.hi = _bounds([p.lo for p in pieces] + [p.hi for p in pieces])
    self.left: Optional[_Node] = None
    self.right: Optional[_Node] = None
    self.pieces: List[Piece] = []
    if len(pieces) <= 4:
      self.pieces = pieces
      return
    axis = max(range(3), key=lambda k: self.hi[k] - self.lo[k])
    pieces = sorted(pieces, key=lambda p: p.lo[axis] + p.hi[axis])
    half = len(pieces) // 2
    self.left, self.right = _Node(pieces[:half]), _Node(pieces[half:])


def _meets(lo: Vec, hi: Vec, lo2: Vec, hi2: Vec) -> bool:
  return all(lo[k] <= hi2[k] and lo2[k] <= hi[k] for k in range(3))


class Obstacles:
  """The pieces that stand still, in a bounding-volume tree."""

  def __init__(self, pieces: List[Piece]):
    self.pieces = pieces
    self._root = _Node(pieces) if pieces else None
    self.visited = 0  # boxes looked at, to show the tree keeps queries small

  def near(self, lo: Vec, hi: Vec) -> List[Piece]:
    """The pieces whose boxes meet the box from `lo` to `hi`."""
    found: List[Piece] = []
    stack = [self._root] if self._root is not None else []
    while stack:
      node = stack.pop()
      self.visited += 1
      if not _meets(lo, hi, node.lo, node.hi):
        continue
      if node.left is None:
        found.extend(p for p in node.pieces if _meets(lo, hi, p.lo, p.hi))
      else:
        stack.append(node.left)
        if node.right is not None:
          stack.append(node.right)
    return found


# -- motions -------------------------------------------------------------------------------------


@dataclasses.dataclass
class Segment:
  """A stretch of a group's way: the hull of its pieces at `poses`, grown by `slack`, taken over
  `start` to `end` in time."""

  poses: List[Pose]
  slack: float = 0.0
  start: float = 0.0
  end: float = 1.0


@dataclasses.dataclass
class Group:
  """Things that move together, rigidly: their solid pieces as they are now, and their way, as
  segments of poses relative to now."""

  name: str
  pieces: List[Piece]
  segments: List[Segment]

  def swept(self, k: int) -> List[Tuple[Piece, List[Vec], float]]:
    """Each piece's hull over segment `k`, and its slack."""
    segment = self.segments[k]
    return [
      (piece, [pose.apply(p) for pose in segment.poses for p in piece.points], segment.slack)
      for piece in self.pieces
    ]


def moving(
  name: str,
  resources: Iterable[Resource],
  segments: List[Segment],
  leave_out: Iterable[Resource] = (),
) -> Group:
  """A group of `resources`, each with everything under it but `leave_out`, moving along
  `segments`."""
  out = {id(r) for r in leave_out}
  return Group(name, [p for r in resources for p in solid_pieces(r, out)], segments)


def straight(shift: Vec, start: float = 0.0, end: float = 1.0) -> List[Segment]:
  """A straight move by `shift`: exact."""
  return [Segment([STILL, Pose(shift=shift)], 0.0, start, end)]


def on_axes(shift: Vec, start: float = 0.0, end: float = 1.0) -> List[Segment]:
  """A move by `shift` with each axis on its own profile, so along no known line: the box it spans."""
  corners = {(x, y, z) for x in (0.0, shift[0]) for y in (0.0, shift[1]) for z in (0.0, shift[2])}
  return [Segment([Pose(shift=c) for c in sorted(corners)], 0.0, start, end)]


def turn_slack(radius: float, degrees: float) -> float:
  """How far from the chord a point `radius` from a pivot strays, turning `degrees`."""
  return radius * (1.0 - math.cos(math.radians(abs(degrees)) / 2.0))


def turning(
  pieces: Sequence[Piece],
  pivot: Vec,
  degrees: float,
  step: float = 5.0,
  start: float = 0.0,
  end: float = 1.0,
  shift: Vec = (0.0, 0.0, 0.0),
) -> List[Segment]:
  """A turn of `degrees` about the vertical through `pivot` - shifted by `shift` along the way, in
  step - cut into arcs of at most `step` degrees, each grown by the most any piece strays."""
  n = max(1, math.ceil(abs(degrees) / step))
  radius = max(
    (math.hypot(p[0] - pivot[0], p[1] - pivot[1]) for piece in pieces for p in piece.points),
    default=0.0,
  )
  slack = turn_slack(radius, degrees / n)
  poses = [Pose(degrees * k / n, pivot, _scale(shift, k / n)) for k in range(n + 1)]
  return [
    Segment(
      [poses[k], poses[k + 1]],
      slack,
      start + (end - start) * k / n,
      start + (end - start) * (k + 1) / n,
    )
    for k in range(n)
  ]


def trapezoid(
  distance_mm: float, speed: float, acceleration: Optional[float]
) -> Tuple[float, Callable[[float], float]]:
  """A trapezoidal (or triangular) profile over `distance_mm`: its duration, and the distance
  covered by a time."""
  d = abs(distance_mm)
  if d == 0 or speed <= 0:
    return 0.0, lambda t: 0.0
  if not acceleration:
    return d / speed, lambda t: min(d, max(0.0, t) * speed)
  ramp = speed / acceleration
  if acceleration * ramp * ramp >= d:  # never reaches speed
    ramp = math.sqrt(d / acceleration)
    speed = acceleration * ramp
    cruise = 0.0
  else:
    cruise = (d - acceleration * ramp * ramp) / speed
  total = 2 * ramp + cruise

  def covered(t: float) -> float:
    t = min(max(t, 0.0), total)
    if t < ramp:
      return 0.5 * acceleration * t * t
    if t < ramp + cruise:
      return 0.5 * acceleration * ramp * ramp + speed * (t - ramp)
    left = total - t
    return d - 0.5 * acceleration * left * left

  return total, covered


def profiled(
  shift: Vec,
  speed: float,
  acceleration: Optional[float] = None,
  start: float = 0.0,
  slices: int = 8,
) -> List[Segment]:
  """A straight move by `shift` on a trapezoidal profile starting at `start` s, cut into `slices`
  of equal time, so that two things moving at once are compared only while both are there."""
  length = math.sqrt(_dot(shift, shift))
  total, covered = trapezoid(length, speed, acceleration)
  if length == 0:
    return [Segment([STILL], 0.0, start, start)]
  unit = _scale(shift, 1.0 / length)
  times = [total * k / slices for k in range(slices + 1)]
  poses = [Pose(shift=_scale(unit, covered(t))) for t in times]
  return [
    Segment([poses[k], poses[k + 1]], 0.0, start + times[k], start + times[k + 1])
    for k in range(slices)
  ]


# -- the check -----------------------------------------------------------------------------------


@dataclasses.dataclass
class Collision:
  mover: Resource
  obstacle: Resource
  group: str
  segment: int
  gap: float  # how far apart they come, in mm: 0 when they meet
  other_group: Optional[str] = None

  def __str__(self) -> str:
    against = f" (moving with {self.other_group})" if self.other_group else ""
    return (
      f"{self.mover.name} ({self.group}, segment {self.segment}) comes within {self.gap:.2f} mm of "
      f"{self.obstacle.name}{against}"
    )


def check(
  root: Resource,
  groups: Sequence[Group],
  clearance: float = 0.0,
  allow: Iterable[Resource] = (),
  obstacles: Optional[Obstacles] = None,
  between_groups: bool = True,
) -> List[Collision]:
  """Every place where something moving in `groups` comes within `clearance` of something standing
  still under `root`, or of something in another group at the same time.

  Args:
    root: what the moves happen in, a deck or everything around it.
    groups: what moves, and how.
    clearance: how close is too close, in mm. 0 reports only things that meet.
    allow: things meant to be touched - what is picked up, where it is put down: never reported.
    obstacles: the pieces standing still, if already worked out (`Obstacles(solid_pieces(...))`,
      leaving out everything in `groups`).
    between_groups: whether to check the groups against each other too, over the times they share.
  """
  allowed = {id(r) for r in allow}
  if obstacles is None:
    leave_out = {id(piece.resource) for g in groups for piece in g.pieces}
    obstacles = Obstacles(solid_pieces(root, leave_out))
  reach = max(clearance, 0.0)
  found: List[Collision] = []
  seen: Set[Tuple[int, int, str]] = set()

  def report(mover: Piece, obstacle: Resource, group: str, k: int, gap: float, other=None) -> None:
    key = (id(mover.resource), id(obstacle), group)
    if key not in seen:
      seen.add(key)
      found.append(Collision(mover.resource, obstacle, group, k, max(gap, 0.0), other))

  for group in groups:
    for k in range(len(group.segments)):
      for piece, hull, slack in group.swept(k):
        lo, hi = _bounds(hull)
        grow = slack + reach
        near = obstacles.near(_sub(lo, (grow,) * 3), _add(hi, (grow,) * 3))
        for other in near:
          if id(other.resource) in allowed:
            continue
          gap = distance(hull, other.points, stop_beyond=slack + reach + 1.0) - slack
          if gap <= 0.0 or gap < reach:
            report(piece, other.resource, group.name, k, gap)

  # Groups against each other, only over the times both segments cover - each group standing where
  # it starts before its first segment, and where it ends after its last.
  def timeline(g: Group) -> Group:
    if not g.segments:
      return Group(g.name, g.pieces, [Segment([STILL], 0.0, -math.inf, math.inf)])
    first, last = g.segments[0], g.segments[-1]
    return Group(
      g.name,
      g.pieces,
      [Segment(first.poses[:1], 0.0, -math.inf, first.start)]
      + g.segments
      + [Segment(last.poses[-1:], 0.0, last.end, math.inf)],
    )

  timelines = [timeline(g) for g in groups] if between_groups else []
  for i, a in enumerate(timelines):
    for b in timelines[i + 1 :]:
      for ka, sa in enumerate(a.segments):
        for kb, sb in enumerate(b.segments):
          if min(sa.end, sb.end) <= max(sa.start, sb.start):
            continue
          hulls_b = b.swept(kb)
          for pa, hull_a, slack_a in a.swept(ka):
            for pb, hull_b, slack_b in hulls_b:
              if id(pa.resource) in allowed or id(pb.resource) in allowed:
                continue
              gap = distance(hull_a, hull_b) - slack_a - slack_b
              if gap <= 0.0 or gap < reach:
                report(pa, pb.resource, a.name, ka, gap, b.name)
  return found


def pieces_by_name(pieces: Iterable[Piece]) -> Dict[str, List[Piece]]:
  by: Dict[str, List[Piece]] = {}
  for p in pieces:
    by.setdefault(p.resource.name, []).append(p)
  return by
