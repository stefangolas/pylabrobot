"""Moving plates and lids with the CO-RE grip tools, the model kept as they go.

The channels' own layer (`Pipettes.core_grip_plate`, `core_move_gripped_plate`,
`core_release_plate`) grips, carries and lets go at positions, each checked against where the
channels reach before anything is sent. This is the layer above it, as `iSWAPTransport` is above
the iSWAP: it works out those positions from resources, and keeps the model. While held, a
resource hangs from the front tool channel's shaft, so it rides with the channels; let go, it is
placed on what it was put down on as PyLabRobot places it there (`place`), as the iSWAP does.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional, Union

from pylabrobot.hamilton.star.driver.features.iswap_transport import place, placement
from pylabrobot.hamilton.star.driver.features.pipettes import (
  core_tool_face_distance,
)
from pylabrobot.resources.coordinate import Coordinate
from pylabrobot.resources.hamilton.core_gripper_tools import HamiltonCoreGripperTool
from pylabrobot.resources.lid import Lid
from pylabrobot.resources.resource import Resource

if TYPE_CHECKING:
  from pylabrobot.hamilton.star.driver.features.pipettes import Pipettes


def hanging_location(
  shaft: Resource, tool: HamiltonCoreGripperTool, resource: Resource, from_top: float
) -> Coordinate:
  """Where a gripped resource hangs in the front tool channel's shaft's frame: centred on the
  channel's axis in X, its front side against the tool's face, its grip line `from_top` below its
  top. The tool sits on the shaft as `TipMountingShaft.mount_tip` puts it, its grip line
  `core_tool_grip_line_overhang` below the shaft's stop disc."""
  pick_up = tool.pick_up_location or tool.get_anchor("c", "c", "t")
  grip_line = tool.fitting_depth - pick_up.z + tool.grip_line_height
  return Coordinate(
    shaft.get_size_x() / 2 - resource.get_size_x() / 2,
    shaft.get_size_y() / 2 + core_tool_face_distance(tool),
    grip_line - (resource.get_size_z() - from_top),
  )


@dataclass
class _Held:
  resource: Resource
  from_top: float


class COREGripper:
  """The CO-RE grip tools as a gripper of resources.

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

  async def _tools(self) -> None:
    if not self.pipettes.get_core_gripper_channels():
      front = self.pipettes.num_channels - 1 if self.front_channel is None else self.front_channel
      await self.pipettes.pick_up_core_gripper_tools(front_channel=front)

  @staticmethod
  def _from_top(resource: Resource, pickup_distance_from_top: Optional[float]) -> float:
    """As asked, or 5 mm; below a lid's skirt for a plate with a lid on."""
    lid = getattr(resource, "lid", None)
    skirt = lid.nesting_z_height if isinstance(lid, Lid) else 0.0
    if pickup_distance_from_top is None:
      return max(5.0, skirt + 1.0)
    return pickup_distance_from_top

  def _front_shaft_and_tool(self):
    back, front, tool = self.pipettes._core_grip_channels()
    shaft = self.pipettes.shaft(front)
    assert shaft is not None
    return shaft, tool

  async def pick_up_resource(
    self,
    resource: Resource,
    pickup_distance_from_top: Optional[float] = None,
    offset: Coordinate = Coordinate.zero(),
    **kwargs,
  ) -> None:
    """Grip `resource` and lift it, picking the tools up first when no channel carries them.
    `kwargs` go to `Pipettes.core_grip_plate`.

    Raises:
      RuntimeError: If something is already held.
      ValueError: If it cannot be reached (nothing is sent; the tools may have been picked up).
    """
    if self._held is not None:
      raise RuntimeError(f"already holding {self._held.resource.name}")
    from_top = self._from_top(resource, pickup_distance_from_top)
    centre = resource.get_location_wrt(self.deck, x="c", y="c", z="b") + offset
    grip = Coordinate(centre.x, centre.y, centre.z + resource.get_absolute_size_z() - from_top)
    if not self.pipettes.get_core_gripper_channels():
      # Asked of the channels' gate before the tools are fetched for a grip they cannot make.
      parked = self.pipettes.core_gripper_holder().front_tool
      self.pipettes._check_core_grip_reachable(
        grip, resource.get_absolute_size_y(), (grip.z,), parked
      )
    await self._tools()
    shaft, tool = self._front_shaft_and_tool()
    hanging = hanging_location(shaft, tool, resource, from_top)
    # For whoever acts the command out (the viewer): what is taken, and where it will hang.
    self.pipettes._core_handover = (resource, shaft, hanging)
    await self.pipettes.core_grip_plate(grip, resource.get_absolute_size_y(), **kwargs)
    resource.unassign()
    shaft.assign_child_resource(resource, location=hanging)
    self._held = _Held(resource, from_top)

  async def move_picked_up_resource(self, centre: Coordinate, **kwargs) -> None:
    """Carry what is held so its centre is over `centre`, the grip line at `centre.z`."""
    if self._held is None:
      raise RuntimeError("nothing is held")
    self.pipettes._core_handover = None
    await self.pipettes.core_move_gripped_plate(
      centre, self._held.resource.get_absolute_size_y(), **kwargs
    )

  async def drop_resource(
    self,
    destination: Union[Resource, Coordinate],
    offset: Coordinate = Coordinate.zero(),
    return_tools: bool = False,
    **kwargs,
  ) -> None:
    """Put what is held down on `destination` and let go. `kwargs` go to
    `Pipettes.core_release_plate`.

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
    grip = Coordinate(centre.x, centre.y, corner.z + resource.get_absolute_size_z() - held.from_top)
    if isinstance(destination, Coordinate):
      parent, local = self.deck, corner
    elif destination.category == "trash":
      parent, local = None, None
    else:
      parent, local = destination, corner - destination.get_location_wrt(self.deck)
    self.pipettes._core_handover = (resource, parent, local)
    await self.pipettes.core_release_plate(grip, resource.get_absolute_size_y(), **kwargs)
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
    """Pick `resource` up and put it down on `to`."""
    await self.pick_up_resource(resource, pickup_distance_from_top=pickup_distance_from_top)
    await self.drop_resource(to, return_tools=return_tools)
