"""Moving plates and lids with the CO-RE grip tools on two channels: `C0 ZP`, `ZM`, `ZR`.

Two adjacent channels carry the CO-RE grip tools (`Pipettes.pick_up_core_gripper_tools`) and close
on a resource's front and back sides, its middle at the grip line. While held, the resource hangs
from the front tool channel's shaft, so it rides with the channels as the model moves them; let
go, it is placed on what it was put down on as PyLabRobot places it there (`place`), as the iSWAP
does.

The firmware takes the resource's centre (X, Y) and the grip line's height. Every position is
checked against the channels' reach first (`Pipettes._check_reachable`): the channels travel with
the arm, so nothing left of its X travel is reached - not the NGS STAR decks' ODTC, left of track
1, which the iSWAP serves.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional, Union

from pylabrobot.hamilton.star.driver.features.iswap_transport import placement, place
from pylabrobot.hamilton.star.driver.lock import _FirmwareLock
from pylabrobot.resources.coordinate import Coordinate
from pylabrobot.resources.hamilton.core_gripper_tools import HamiltonCoreGripperTool
from pylabrobot.resources.lid import Lid
from pylabrobot.resources.resource import Resource

if TYPE_CHECKING:
  from pylabrobot.hamilton.star.driver.features.pipettes import Pipettes

SQUEEZE = 3.0  # the tools close this much narrower than the resource, and open this much wider
TRAVERSE = 280.0  # legacy's traversal height for gripped moves


def tool_face_distance(tool: HamiltonCoreGripperTool) -> float:
  """How far a grip tool's face stands from its channel's axis, in Y."""
  pick_up = tool.pick_up_location or tool.get_anchor("c", "c", "t")
  return tool.get_size_y() - pick_up.y


def grip_line_overhang(tool: HamiltonCoreGripperTool) -> float:
  """How far a mounted grip tool's grip line hangs below its channel's stop disc, in mm: the height
  the firmware's CO-RE plate commands are given in."""
  pick_up = tool.pick_up_location or tool.get_anchor("c", "c", "t")
  return float(pick_up.z - tool.fitting_depth - tool.grip_line_height)


def hanging_location(
  shaft: Resource, tool: HamiltonCoreGripperTool, resource: Resource, from_top: float
) -> Coordinate:
  """Where a gripped resource hangs in the front tool channel's shaft's frame: centred on the
  channel's axis in X, its front side against the tool's face, its grip line `from_top` below its
  top. The tool sits on the shaft as `TipMountingShaft.mount_tip` puts it."""
  pick_up = tool.pick_up_location or tool.get_anchor("c", "c", "t")
  grip_line = tool.fitting_depth - pick_up.z + tool.grip_line_height
  return Coordinate(
    shaft.get_size_x() / 2 - resource.get_size_x() / 2,
    shaft.get_size_y() / 2 + tool_face_distance(tool),
    grip_line - (resource.get_size_z() - from_top),
  )


@dataclass
class _Held:
  resource: Resource
  from_top: float


class COREGripper:
  """The CO-RE grip tools as a plate gripper.

  Args:
    pipettes: the channels that carry the tools.
    front_channel: the front one of the two tool channels, 0-indexed from the back. The front-most
      channel when None.
  """

  def __init__(self, pipettes: "Pipettes", front_channel: Optional[int] = None):
    self.pipettes = pipettes
    self.front_channel = front_channel
    self._held: Optional[_Held] = None

  @property
  def deck(self) -> Resource:
    deck = self.pipettes._driver.deck
    if deck is None:
      raise RuntimeError("resources are moved on the deck; this driver was given none")
    return deck

  def _front(self) -> int:
    return self.pipettes.num_channels - 1 if self.front_channel is None else self.front_channel

  async def _require_iswap_parked(self) -> None:
    iswap = getattr(self.pipettes._driver, "iswap", None)
    if iswap is not None and not await iswap.request_is_parked():
      raise RuntimeError("the iSWAP is not parked; the channels move where it stands")

  async def _ensure_tools(self) -> HamiltonCoreGripperTool:
    channels = self.pipettes.get_core_gripper_channels()
    if not channels:
      await self.pipettes.pick_up_core_gripper_tools(front_channel=self._front())
      channels = self.pipettes.get_core_gripper_channels()
    tool = self.pipettes.get_mounted_tool(channels[-1])
    assert isinstance(tool, HamiltonCoreGripperTool)
    return tool

  def _check_reachable(self, centre: Coordinate, grip_z: float, width: float, traverse: float):
    """Raise unless both tool channels can reach a grip centred at `centre`, `width` across, its
    grip line at `grip_z`, travelling with the grip line at `traverse`. Every axis goes through the
    channels' gate (`Pipettes._check_reachable`, `_check_tool_bottom_reachable`).

    Raises:
      ValueError: If they cannot.
    """
    tool = self._tool()
    half = width / 2 + tool_face_distance(tool)
    self.pipettes._check_reachable("x", centre.x)
    self.pipettes._check_reachable("y", centre.y - half)
    self.pipettes._check_reachable("y", centre.y + half)
    for z in (grip_z, traverse):
      self.pipettes._check_tool_bottom_reachable(z, grip_line_overhang(tool))

  def _tool(self) -> HamiltonCoreGripperTool:
    """The front grip tool: on its channel, or still parked in the holder."""
    channels = self.pipettes.get_core_gripper_channels()
    tool = (
      self.pipettes.get_mounted_tool(channels[-1])
      if channels
      else self.pipettes.core_gripper_holder().front_tool
    )
    if not isinstance(tool, HamiltonCoreGripperTool):
      raise RuntimeError("no CO-RE grip tool on the channels or in the holder")
    return tool

  @staticmethod
  def _from_top(resource: Resource, pickup_distance_from_top: Optional[float]) -> float:
    """As asked, or 5 mm; below a lid's skirt for a plate with a lid on."""
    lid = getattr(resource, "lid", None)
    skirt = lid.nesting_z_height if isinstance(lid, Lid) else 0.0
    if pickup_distance_from_top is None:
      return max(5.0, skirt + 1.0)
    return pickup_distance_from_top

  async def pick_up_resource(
    self,
    resource: Resource,
    pickup_distance_from_top: Optional[float] = None,
    offset: Coordinate = Coordinate.zero(),
    grip_strength: int = 15,
    y_gripping_speed: float = 5.0,
    z_speed: float = 50.0,
    traverse_height: float = TRAVERSE,
  ) -> None:
    """Close the tools on `resource`'s front and back sides and lift it. `C0 ZP`. Picks up the
    tools first when no channel carries them.

    Raises:
      RuntimeError: If something is already held, or the iSWAP is not parked.
    """
    if self._held is not None:
      raise RuntimeError(f"already holding {self._held.resource.name}")
    from_top = self._from_top(resource, pickup_distance_from_top)
    centre = resource.get_location_wrt(self.deck, x="c", y="c", z="b") + offset
    grip_z = centre.z + resource.get_absolute_size_z() - from_top
    width = resource.get_absolute_size_y()
    self._check_reachable(centre, grip_z, width, traverse_height)
    await self._require_iswap_parked()
    tool = await self._ensure_tools()
    shaft = self.pipettes.shaft(self.pipettes.get_core_gripper_channels()[-1])
    assert shaft is not None
    hanging = hanging_location(shaft, tool, resource, from_top)
    # For whoever acts the command out (the viewer): what is taken, and where it will hang.
    self.pipettes._core_handover = (resource, shaft, hanging)
    await self.pipettes._driver.send_command(
      module="C0",
      command="ZP",
      subsystem=_FirmwareLock.CHANNELS,
      xs=f"{abs(round(centre.x * 10)):05}",
      xd=0,
      yj=f"{round(centre.y * 10):04}",
      yv=f"{round(y_gripping_speed * 10):04}",
      zj=f"{round(grip_z * 10):04}",
      zy=f"{round(z_speed * 10):04}",
      yo=f"{round((width + SQUEEZE) * 10):04}",
      yg=f"{round((width - SQUEEZE) * 10):04}",
      yw=f"{grip_strength:02}",
      th=f"{round(traverse_height * 10):04}",
      te=f"{round(traverse_height * 10):04}",
    )
    resource.unassign()
    shaft.assign_child_resource(resource, location=hanging)
    self._held = _Held(resource, from_top)

  async def move_picked_up_resource(
    self, centre: Coordinate, z_speed: float = 50.0, traverse_height: float = TRAVERSE
  ) -> None:
    """Carry what is held so its centre is over `centre` and its grip line at `centre.z`.
    `C0 ZM`."""
    if self._held is None:
      raise RuntimeError("nothing is held")
    self._check_reachable(
      centre, centre.z, self._held.resource.get_absolute_size_y(), traverse_height
    )
    await self.pipettes._driver.send_command(
      module="C0",
      command="ZM",
      subsystem=_FirmwareLock.CHANNELS,
      xs=f"{abs(round(centre.x * 10)):05}",
      xd=0,
      xg=4,
      yj=f"{round(centre.y * 10):04}",
      zj=f"{round(centre.z * 10):04}",
      zy=f"{round(z_speed * 10):04}",
      th=f"{round(traverse_height * 10):04}",
    )

  async def drop_resource(
    self,
    destination: Union[Resource, Coordinate],
    offset: Coordinate = Coordinate.zero(),
    traverse_height: float = TRAVERSE,
    end_height: float = TRAVERSE,
    return_tools: bool = False,
  ) -> None:
    """Put what is held down on `destination` and open the tools. `C0 ZR`.

    Args:
      destination: what to put it on - a site, a plate adapter, a stack, a plate for a lid, the
        trash - or a place on the deck, its left front bottom corner.
      return_tools: put the tools back in their holder after.
    """
    held = self._held
    if held is None:
      raise RuntimeError("nothing is held")
    resource = held.resource
    if isinstance(destination, Resource):
      destination.check_can_drop_resource_here(resource)
    _, corner = placement(self.deck, resource, destination, 0.0)
    centre = corner + resource.center() + offset
    grip_z = corner.z + resource.get_absolute_size_z() - held.from_top
    self._check_reachable(centre, grip_z, resource.get_absolute_size_y(), traverse_height)
    # For whoever acts the command out (the viewer): where it will be let go, and on what.
    if isinstance(destination, Coordinate):
      parent, local = self.deck, corner
    elif destination.category == "trash":
      parent, local = None, None
    else:
      parent, local = destination, corner - destination.get_location_wrt(self.deck)
    self.pipettes._core_handover = (resource, parent, local)
    await self.pipettes._driver.send_command(
      module="C0",
      command="ZR",
      subsystem=_FirmwareLock.CHANNELS,
      xs=f"{abs(round(centre.x * 10)):05}",
      xd=0,
      yj=f"{round(centre.y * 10):04}",
      zj=f"{round(grip_z * 10):04}",
      zi="000",
      zy="0500",
      yo=f"{round((resource.get_absolute_size_y() + SQUEEZE) * 10):04}",
      th=f"{round(traverse_height * 10):04}",
      te=f"{round(end_height * 10):04}",
    )
    place(self.deck, resource, destination, resource.rotation.z)
    self._held = None
    if return_tools:
      await self.pipettes.return_core_gripper_tools()

  async def move_resource(
    self,
    resource: Resource,
    to: Union[Resource, Coordinate],
    pickup_distance_from_top: Optional[float] = None,
    return_tools: bool = False,
  ) -> None:
    """Pick `resource` up and put it down on `to`: `C0 ZP` then `C0 ZR`."""
    await self.pick_up_resource(resource, pickup_distance_from_top=pickup_distance_from_top)
    await self.drop_resource(to, return_tools=return_tools)
