"""What a STAR's firmware commands ask its drives to do, in the resource tree's frames.

PyLabRobot records where the arm and the channels are once a command has run. How they got there is
the device's own business: its motion controller works it out from the command. The page acts that
out, and needs the command's targets to do it.

`star_motion` reads one command and returns those targets as local positions of the resources that
model the drives, so the page can move them without knowing anything about firmware. A command that
moves nothing, or one this does not read, returns None.

Everything here comes from the driver or from the command itself, with one exception: the driver
states no speed or acceleration for the X-arm, so X moves at the threejs visualizer's rate.

- Channel Y and Z speeds, and Z acceleration, are the channels' defaults (`Pipettes.default_*`).
  Y is stated only as an acceleration level, not a rate, and the simulator times a Y move at its
  speed alone, so Y moves at constant speed here too.
- The stroke of a tip command is the one the simulator records (`_record_tip_command`): across, with
  the arm and the channels moving at once, down onto the spots, and back up.
- An aspiration dwells for as long as its own volume and flow rate say, plus its settling time, and
  leaves the liquid at its own swap speed.
- An iSWAP command moves one drive or two, each at the speed and acceleration the command carries,
  converted by the arm's own configuration. The elbow's Y is stated only as a level, so it too moves
  at constant speed. A joint turns about the pivot the driver turns it about (`proximal_joint`).

Heights: the firmware positions the lowest point of what a channel carries, while a channel's
resource is placed by its stop disc, which sits higher by the length of a mounted tip. Every Z here
is converted to the stop disc, with the overhang the channel has when the move is made.
"""

from typing import Any, Dict, List, Optional, Sequence

from pylabrobot.resources.coordinate import Coordinate
from pylabrobot.resources.tip_rack import TipSpot, resting_location

# The driver states no X speed or acceleration; these are the threejs visualizer's, in mm/s and
# mm/s^2.
X_SPEED = 400.0
X_ACCELERATION = 500.0

# How close a command's position has to be to a tip spot's centre to be taken as that spot, in mm.
SPOT_TOLERANCE = 1.0

# `TipDropMethod.DROP`, as `C0 TR` sends it in `ti`.
TIP_DROP = 1


def _pipetting_arm(driver: Any) -> Optional[Any]:
  """The arm carrying the channels, or None when there is none or nothing models it yet."""
  arm = next((a for a in getattr(driver, "arms", []) if a.pipettes is not None), None)
  if arm is None or arm.resource is None or not arm.pipettes.resources:
    return None
  return arm


def _xyz(coordinate: Any) -> Dict[str, float]:
  return {"x": float(coordinate.x), "y": float(coordinate.y), "z": float(coordinate.z)}


def _tenths(value: Any) -> float:
  return int(value) / 10


def _as_list(value: Any) -> List[Any]:
  """A per-channel parameter as a list; `JY` sends its values as one space-separated string."""
  if isinstance(value, str):
    return value.split()
  return list(value)


def _involved(pattern: Sequence[Any]) -> List[int]:
  return [i for i, used in enumerate(pattern) if used in (True, 1, "1")]


class _Frames:
  """Converts the positions the drives report into where the resources modelling them sit."""

  def __init__(self, driver: Any, arm: Any):
    self.driver = driver
    self.arm = arm
    self.pipettes = arm.pipettes
    self.channels = arm.pipettes.resources
    self.deck = driver.deck
    self.on_arm = [c.parent.get_location_wrt(self.deck) for c in self.channels]
    self.anchors = [self.pipettes._reference_anchor(c) for c in self.channels]

  def overhang(self, channel: int) -> float:
    """How far what a channel carries hangs below its stop disc, in mm."""
    below = getattr(self.pipettes, "_below_stop_disc", None)
    return float(below(channel)) if below is not None else 0.0

  def arm_x(self, x: float) -> float:
    return round(float(x - self.arm.configuration.reference_point_from_left), 2)

  def channel_y(self, channel: int, y: float) -> float:
    return round(float(y - self.on_arm[channel].y - self.anchors[channel].y), 2)

  def channel_z(self, channel: int, stop_disc_z: float) -> float:
    return round(float(stop_disc_z - self.on_arm[channel].z - self.anchors[channel].z), 2)

  def lowest_point_z(self, channel: int, z: float, overhang: Optional[float] = None) -> float:
    """A firmware height, the lowest point, as the channel's local Z."""
    return self.channel_z(channel, z + (self.overhang(channel) if overhang is None else overhang))

  def current_y(self, channel: int) -> float:
    """Where the channel's reference point is along Y, in mm on the deck."""
    location = self.channels[channel].location
    return float(location.y + self.on_arm[channel].y + self.anchors[channel].y)

  def planned_ys(self, targets: Dict[int, float]) -> Dict[int, float]:
    """Every channel's Y once the named ones are at their targets, on one rail.

    The others are pushed only as far as the spacing asks, the rule the device goes by. Channel 0
    is at the back, so Y falls as the channel number rises.
    """
    ys = [self.current_y(c) for c in range(len(self.channels))]
    for channel, y in targets.items():
      ys[channel] = y

    def gap(i: int, j: int) -> float:
      return float(self.pipettes._min_pair_spacing(i, j))

    named = sorted(targets)
    if not named:
      return {}
    for c in range(named[-1] + 1, len(ys)):  # in front of the frontmost named channel
      ys[c] = min(ys[c], ys[c - 1] - gap(c - 1, c))
    for c in range(named[0] - 1, -1, -1):  # behind the backmost
      ys[c] = max(ys[c], ys[c + 1] + gap(c, c + 1))
    return {c: round(y, 2) for c, y in enumerate(ys)}

  def shaft(self, channel: int) -> Optional[Any]:
    return next(
      (
        child for child in self.channels[channel].children if child.category == "tip_mounting_shaft"
      ),
      None,
    )

  def spot_at(self, x: float, y: float) -> Optional[TipSpot]:
    """The tip spot centred at (x, y) on the deck, or None."""
    for resource in self.deck.get_all_children():
      if not isinstance(resource, TipSpot):
        continue
      centre = resource.get_location_wrt(self.deck, "c", "c", "b")
      if abs(centre.x - x) <= SPOT_TOLERANCE and abs(centre.y - y) <= SPOT_TOLERANCE:
        return resource
    return None

  def drives(self) -> Dict[str, Dict[str, Optional[float]]]:
    p = self.pipettes
    return {
      "x": {"speed": X_SPEED, "acceleration": X_ACCELERATION},
      "y": {"speed": p.default_y_speed, "acceleration": None},
      "z": {"speed": p.default_z_speed, "acceleration": p.default_z_acceleration},
    }


def _request(frames: _Frames, kind: str, command: str) -> Dict[str, Any]:
  return {
    "kind": kind,
    "command": command,
    "arm": None,
    "channels": [],
    "traverse": [],
    "attach": [],
    "dwell": 0.0,
    "drives": frames.drives(),
    "moves": [],
    "turns": [],
    "jaws": None,
  }


def _channel(frames: _Frames, channel: int, **targets: Optional[float]) -> Dict[str, Any]:
  return {"name": frames.channels[channel].name, "channel": channel, **targets}


def _stroke(
  frames: _Frames,
  kind: str,
  command: str,
  params: Dict[str, Any],
  traverse: float,
  down: Dict[int, float],
  end: Dict[int, float],
  extra: Optional[Dict[int, Dict[str, float]]] = None,
) -> Dict[str, Any]:
  """A command that travels at a height, goes down onto its targets and comes back up.

  `traverse` is a firmware height; `down` and `end` are already local Z, keyed by channel. `extra`
  adds fields to a channel's entry.
  """
  pattern = _as_list(params["tm"])
  involved = _involved(pattern)
  xs, ys = _as_list(params["xp"]), _as_list(params["yp"])
  request = _request(frames, kind, command)
  if not involved:
    return request
  # The arm ends over the last column the command visited, as the simulator records it.
  request["arm"] = {"name": frames.arm.resource.name, "x": frames.arm_x(_tenths(xs[involved[-1]]))}
  planned = frames.planned_ys({c: _tenths(ys[c]) for c in involved})
  request["traverse"] = [
    _channel(frames, c, z=frames.lowest_point_z(c, traverse)) for c in range(len(frames.channels))
  ]
  request["channels"] = [
    _channel(
      frames,
      c,
      y=frames.channel_y(c, y),
      down=down.get(c),
      end=end.get(c),
      **(extra or {}).get(c, {}),
    )
    for c, y in planned.items()
  ]
  return request


def _mounted_location(shaft: Any, tip: Any) -> Dict[str, float]:
  """Where a tip sits on a shaft once picked up, as `TipMountingShaft` places it: its pick-up
  location `fitting_depth` up the shaft's axis."""
  grip = (tip.pick_up_location or tip.get_anchor("c", "c", "t")).rotated(tip.rotation)
  return _xyz(
    Coordinate(
      shaft.get_size_x() / 2 - grip.x,
      shaft.get_size_y() / 2 - grip.y,
      tip.fitting_depth - grip.z,
    )
  )


def _handover(tip: Any, parent: Any, location: Optional[Dict[str, float]]) -> Dict[str, Any]:
  """A tip changing hands at the bottom of a stroke, placed where the model will place it."""
  return {
    "name": tip.name,
    "parent": None if parent is None else parent.name,
    "location": location,
    "rotation": _xyz(tip.rotation),
  }


def _positions(params: Dict[str, Any], channel: int) -> Any:
  return _tenths(_as_list(params["xp"])[channel]), _tenths(_as_list(params["yp"])[channel])


def _tip_pickup(frames: _Frames, command: str, params: Dict[str, Any]) -> Dict[str, Any]:
  involved = _involved(_as_list(params["tm"]))
  tip_length = getattr(frames.driver, "defined_tip_lengths", {}).get(int(params["tt"]), 0.0)
  request = _stroke(
    frames,
    "tip_pickup",
    command,
    params,
    traverse=_tenths(params["th"]),
    down={c: frames.lowest_point_z(c, _tenths(params["tz"])) for c in involved},
    # It comes away carrying the tip, which then hangs below the stop disc.
    end={c: frames.lowest_point_z(c, _tenths(params["th"]), tip_length) for c in involved},
  )
  # At the bottom of the stroke each channel takes the tip in the spot under it onto its shaft.
  for c in involved:
    spot, shaft = frames.spot_at(*_positions(params, c)), frames.shaft(c)
    if spot is not None and spot.tip is not None and shaft is not None:
      request["attach"].append(_handover(spot.tip, shaft, _mounted_location(shaft, spot.tip)))
  return request


def _tip_drop(frames: _Frames, command: str, params: Dict[str, Any]) -> Dict[str, Any]:
  involved = _involved(_as_list(params["tm"]))
  # With `DROP` the heights are the stop disc's, not the lowest point's (`_unchecked_fw_drop_tips`):
  # the tip still on it hangs below them.
  drop = int(params.get("ti", 0)) == TIP_DROP
  request = _stroke(
    frames,
    "tip_drop",
    command,
    params,
    traverse=_tenths(params["th"]),
    down={
      c: frames.lowest_point_z(c, _tenths(params["tz"]), 0.0 if drop else None) for c in involved
    },
    # It comes away empty.
    end={c: frames.lowest_point_z(c, _tenths(params["te"]), 0.0) for c in involved},
  )
  # At the bottom of the stroke each channel leaves its tip in the spot under it, or, over
  # somewhere that is not a spot - the waste - where it is.
  for c in involved:
    shaft = frames.shaft(c)
    if shaft is None or shaft.tip is None:
      continue
    spot = frames.spot_at(*_positions(params, c))
    if spot is not None and spot.tip is None:
      request["attach"].append(_handover(shaft.tip, spot, _xyz(resting_location(spot, shaft.tip))))
    else:
      request["attach"].append(_handover(shaft.tip, None, None))
  return request


def _aspirate(frames: _Frames, command: str, params: Dict[str, Any]) -> Dict[str, Any]:
  involved = _involved(_as_list(params["tm"]))

  # Lists other than the positions run over the channels involved, in order.
  def per_channel(field: str) -> Dict[int, float]:
    values = _as_list(params[field])
    return {c: _tenths(values[i]) for i, c in enumerate(involved)}

  surface = per_channel("zl")
  immersion = per_channel("ip")
  floor = per_channel("zx")
  swap_speed = per_channel("de")
  down = {c: max(surface[c] - immersion[c], floor[c]) for c in involved}
  request = _stroke(
    frames,
    "aspirate",
    command,
    params,
    traverse=_tenths(params["th"]),
    down={c: frames.lowest_point_z(c, down[c]) for c in involved},
    end={c: frames.lowest_point_z(c, _tenths(params["te"])) for c in involved},
    # Out of the liquid at the command's swap speed, before rising at the drive's own.
    extra={
      c: {"leave": frames.lowest_point_z(c, surface[c]), "leave_speed": swap_speed[c]}
      for c in involved
      if swap_speed[c] > 0
    },
  )
  # As long as the slowest channel takes to draw its volume, and settle.
  volumes, speeds, settle = per_channel("av"), per_channel("as_"), per_channel("wt")
  request["dwell"] = round(
    max((volumes[c] / speeds[c] if speeds[c] else 0.0) + settle[c] for c in involved), 2
  )
  return request


def _move_y(frames: _Frames, command: str, params: Dict[str, Any]) -> Dict[str, Any]:
  request = _request(frames, "move_y", command)
  ys = _as_list(params["yp"])
  request["channels"] = [
    _channel(frames, c, y=frames.channel_y(c, _tenths(y)))
    for c, y in enumerate(ys[: len(frames.channels)])
  ]
  return request


def _move_z(frames: _Frames, command: str, params: Dict[str, Any]) -> Dict[str, Any]:
  request = _request(frames, "move_z", command)
  zs = _as_list(params["zp"])
  request["channels"] = [
    _channel(frames, c, end=frames.lowest_point_z(c, _tenths(z)))
    for c, z in enumerate(zs[: len(frames.channels)])
  ]
  return request


def _move_x(frames: _Frames, driver: Any, command: str, params: Dict[str, Any]) -> Optional[Dict]:
  side = "left" if command == "XP" else "right"
  arm = next((a for a in driver.arms if a.side == side), None)
  if arm is None or arm.resource is None:
    return None
  increments = params.get(f"{arm.parameter_prefix}a")
  if increments is None:
    return None
  x = arm.configuration.x_increments_to_mm(int(increments))
  request = _request(frames, "move_x", command)
  request["arm"] = {
    "name": arm.resource.name,
    "x": round(x - arm.configuration.reference_point_from_left, 2),
  }
  return request


# -- iSWAP ---------------------------------------------------------------------


def _iswap_of(driver: Any) -> Optional[Any]:
  """The iSWAP, or None when there is none or nothing models it yet."""
  for arm in getattr(driver, "arms", []):
    iswap = arm.iswap
    if iswap is not None and None not in (iswap.resource, iswap.link_1, iswap.gripper):
      return iswap
  return None


def _iswap_request(kind: str, command: str) -> Dict[str, Any]:
  return {
    "kind": kind,
    "command": command,
    "arm": None,
    "channels": [],
    "traverse": [],
    "attach": [],
    "dwell": 0.0,
    "drives": {},
    "moves": [],
    "turns": [],
    "jaws": None,
  }


def _elbow_move(driver: Any, iswap: Any, command: str, params: Dict[str, Any]) -> Dict[str, Any]:
  """`R0 YA` or `R0 ZA`: the head the arm hangs from, along Y or Z."""
  c = iswap.configuration
  head = iswap.resource
  on_arm, anchor = head.parent.get_location_wrt(driver.deck), head.reference_point
  request = _iswap_request("iswap_move", "R0" + command)
  if command == "YA":
    y = c.y_increments_to_mm(int(params["ya"]))
    request["moves"].append(
      {
        "name": head.name,
        "axis": 1,
        "to": round(float(y - on_arm.y - anchor.y), 2),
        "speed": c.y_increments_to_mm(int(params["yv"])),
        "acceleration": None,
      }
    )
  else:
    # The drive counts the finger plane; the head's bottom stands above it.
    z = c.z_increments_to_mm(int(params["za"])) + c.elbow_z_offset_above_finger
    request["moves"].append(
      {
        "name": head.name,
        "axis": 2,
        "to": round(float(z - on_arm.z - anchor.z), 2),
        "speed": c.z_increments_to_mm(int(params["zv"])),
        "acceleration": round(int(params["zr"]) * 1000 * c.z_mm_per_increment, 2),
      }
    )
  return request


def _joints(iswap: Any, command: str, params: Dict[str, Any]) -> Dict[str, Any]:
  """`R0 PA`: the elbow and the wrist together, each to its own angle at its own speed.

  A joint's angle is stated as its drive reports it; `base` is what the driver subtracts from it to
  get the resource's rotation (`elbow_drive_update_angle`, `wrist_drive_update_angle`).
  """
  c = iswap.configuration
  request = _iswap_request("iswap_turn", "R0" + command)
  link, gripper = iswap.link_1, iswap.gripper
  request["turns"].append(
    {
      "name": link.name,
      "drive": c.elbow_drive_increments_to_angle(int(params["wa"])),
      "base": 90.0,
      "pivot": _xyz(link.proximal_joint),
      "speed": c.elbow_increments_to_deg_per_sec(int(params["wv"])),
      "acceleration": c.elbow_increments_to_deg_per_sec2(int(params["wr"])),
    }
  )
  if c.wrist_drive_predefined_increments is not None:
    request["turns"].append(
      {
        "name": gripper.name,
        "drive": c.wrist_increments_to_deg(int(params["ta"])),
        "base": c.wrist_increments_to_deg(c.wrist_drive_predefined_increments.straight),
        "pivot": _xyz(gripper.proximal_joint),
        "speed": c.wrist_increments_to_deg_per_sec(int(params["tv"])),
        "acceleration": c.wrist_increments_to_deg_per_sec2(int(params["tr"])),
      }
    )
  return request


def _jaws(
  iswap: Any, command: str, width: float, speed: float, acceleration: float
) -> Optional[Dict[str, Any]]:
  """The fingers stood `width` apart, as `MechanicalGripper._place_the_fingers` stands them.

  Each finger travels half of what the width does, in the same time, so at half the drive's speed.
  The page decides from which way they move whether this closes on something or lets it go.
  """
  gripper = iswap.gripper
  low, high = gripper.jaw_range
  if not low <= width <= high:
    return None  # the model leaves the jaws where they are, and so does the page
  centre = gripper.proximal_joint.y + gripper.tool_center_point.y
  fingers = []
  for finger, side in zip(gripper.fingers, (1.0, -1.0)):
    facing = centre + side * width / 2.0
    fingers.append(
      {"name": finger.name, "y": round(facing if side > 0 else facing - finger.get_size_y(), 3)}
    )
  request = _iswap_request("iswap_jaws", command)
  request["jaws"] = {
    "gripper": gripper.name,
    "width": width,
    "fingers": fingers,
    "speed": speed / 2.0,
    "acceleration": acceleration / 2.0,
    # Where the fingers close, in the gripper's own frame: what they take hold of is there.
    "grip_point": _xyz(gripper.proximal_joint + gripper.tool_center_point),
  }
  return request


def _iswap_motion(
  driver: Any, iswap: Any, module: str, command: str, params: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
  c = iswap.configuration
  if module == "R0" and command in ("YA", "ZA"):
    return _elbow_move(driver, iswap, command, params)
  if module == "R0" and command == "PA":
    return _joints(iswap, command, params)
  if module == "R0" and command == "GA":
    return _jaws(
      iswap,
      "R0GA",
      c.gripper_increments_to_mm(int(params["ga"])),
      c.gripper_increments_to_mm_per_sec(int(params["gv"])),
      c.gripper_increments_to_mm_per_sec2(int(params["gr"])),
    )
  if module == "C0" and command == "GC":
    # Closes onto what is there, at the drive's closing speed; the width is in tenths of a mm.
    return _jaws(
      iswap,
      "C0GC",
      _tenths(params["gb"]),
      c.gripper_increments_to_mm_per_sec(c.gripper_close_speed_default_increments),
      c.gripper_increments_to_mm_per_sec2(c.gripper_acceleration_default_increments),
    )
  return None


def star_motion(
  driver: Any, module: str, command: str, params: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
  """What one STAR firmware command asks the drives to do, as local targets, or None.

  Args:
    driver: the STAR driver the command is going to, which knows the arm and the channels.
    module: the module the command is addressed to.
    command: the two-letter command code.
    params: the command's parameters, as the driver passes them to be assembled.

  Returns:
    A motion request for the page: the command's `kind`; the arm's target X; each channel's
    targets - `y`, the heights `down` and `end`, and for an aspiration where it `leave`s the liquid
    and at what `leave_speed`; the height every channel rises to first (`traverse`); the tips that
    change hands at the bottom of the stroke (`attach`: a tip's name and the resource that takes
    it, or None to leave it where it is); how long the stroke dwells at the bottom; and the drives'
    speeds. None for a command that moves nothing, or one this does not read.
  """
  if command[0] in ("R", "Q"):
    return None
  key = module + command
  try:
    iswap = _iswap_of(driver)
    if iswap is not None and (module == "R0" or key == "C0GC"):
      return _iswap_motion(driver, iswap, module, command, params)
    arm = _pipetting_arm(driver)
    if arm is None:
      return None
    frames = _Frames(driver, arm)
    if key == "C0TP":
      return _tip_pickup(frames, key, params)
    if key == "C0TR":
      return _tip_drop(frames, key, params)
    if key == "C0AS":
      return _aspirate(frames, key, params)
    if key == "C0JY":
      return _move_y(frames, key, params)
    if key == "C0JZ":
      return _move_z(frames, key, params)
    if module == "X0" and command in ("XP", "SP"):
      return _move_x(frames, driver, command, params)
  except (KeyError, IndexError, ValueError, TypeError, RuntimeError):
    # A command shaped otherwise than this reads it is not acted out; the model still records
    # where it ends.
    return None
  return None
