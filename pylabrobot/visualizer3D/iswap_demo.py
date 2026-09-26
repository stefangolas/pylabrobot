"""The iSWAP carrying a plate between two carrier sites, acted out between the commands.

Run it:

    python -m pylabrobot.visualizer3D.iswap_demo

The arm is driven only by the PR's primitive moves - the X-arm, the head's Y and Z, the two joints
and the jaws - each of which the page plays at the speed the command carries. PyLabRobot does not
move a gripped plate, so the page does: it hands the plate to the gripper when the jaws close on it
and to the site under it when they open. Until stopped, the plate goes over and comes back.
"""

import asyncio
import logging
from typing import List

from pylabrobot.resources.coordinate import Coordinate
from pylabrobot.resources.plate import Plate
from pylabrobot.resources.resource import Resource

from .demo import build_facility, star_of
from .server import Viewer3D

# How far above a plate's bottom the jaws take hold of it, in mm.
GRIP_HEIGHT = 7.0
# How much narrower than the plate the jaws close to, in mm: they stop on it.
SQUEEZE = 3.0


def grip_centre(iswap, deck: Resource) -> Coordinate:
  """Where the model has the point the jaws close on, in mm on the deck."""
  gripper = iswap.gripper
  local = (gripper.proximal_joint + gripper.tool_center_point).vector()
  turn = gripper.get_absolute_rotation().get_rotation_matrix()
  base = gripper.get_location_wrt(deck)
  moved = [sum(turn[row][k] * local[k] for k in range(3)) for row in range(3)]
  return Coordinate(base.x + moved[0], base.y + moved[1], base.z + moved[2])


async def move_grip_centre(iswap, deck: Resource, target: Coordinate, axes: str) -> None:
  """Bring the grip centre to `target` along the named axes, the joints held where they are."""
  offset = target - grip_centre(iswap, deck)
  if "x" in axes:
    x = await iswap.arm.request_position()
    await iswap.arm.move_to_x_position(round(x + offset.x, 1))
  if "y" in axes:
    y = await iswap.elbow_request_y_position()
    await iswap.elbow_move_to_y_position(round(y + offset.y, 1))
  if "z" in axes:
    z = await iswap.elbow_request_z_position()
    await iswap.elbow_move_to_z_position(round(z + offset.z, 1))


async def carry(iswap, deck: Resource, plate: Plate, here: Coordinate, there: Coordinate, travel_z):
  """Take the plate whose grip point is `here` to `there`, travelling at `travel_z`."""
  await iswap.gripper_open()
  await move_grip_centre(iswap, deck, Coordinate(here.x, here.y, travel_z), "xy")
  await move_grip_centre(iswap, deck, here, "z")
  await iswap.gripper_move_to_jaw_position(plate.get_size_y() - SQUEEZE)
  await move_grip_centre(iswap, deck, Coordinate(here.x, here.y, travel_z), "z")
  await move_grip_centre(iswap, deck, Coordinate(there.x, there.y, travel_z), "xy")
  await move_grip_centre(iswap, deck, there, "z")
  await iswap.gripper_open()
  await move_grip_centre(iswap, deck, Coordinate(there.x, there.y, travel_z), "z")


def grip_point(site: Resource, plate: Plate, deck: Resource) -> Coordinate:
  """Where the jaws close on `plate` standing on `site`: its middle, `GRIP_HEIGHT` up."""
  seated = plate.location.z if plate.location is not None else 0.0
  return site.get_location_wrt(deck, "c", "c", "b") + Coordinate(0, 0, seated + GRIP_HEIGHT)


async def main() -> None:
  logging.disable(logging.WARNING)
  facility = build_facility()
  star = star_of(facility)
  deck = star.deck
  # An empty site to carry a plate to.
  deck.get_resource("destination_1").unassign()
  await star.setup()
  iswap = star.iswap
  if iswap is None:
    raise RuntimeError("the simulated STARlet has no iSWAP")

  plate = deck.get_resource("source_1")
  assert isinstance(plate, Plate) and plate.parent is not None
  sites: List[Resource] = [plate.parent, deck.get_resource("destination_carrier").children[1]]
  points = [grip_point(site, plate, deck) for site in sites]

  viewer = Viewer3D(facility, name="iswap_demo.py")
  await viewer.start()
  viewer.attach_motion(star.driver)
  print("waiting for a browser to draw the scene")
  await viewer.wait_for_browser()
  await asyncio.sleep(1.0)

  # Clear of the channels, forward, and turned so the jaws close across the plate's short side.
  await iswap.make_space()
  parked = await iswap.elbow_request_y_position()
  travel_z = grip_centre(iswap, deck).z
  await iswap.elbow_move_to_y_position(parked - 200.0)
  await iswap.rotate_to_angles(elbow_absolute_angle="front", gripper_absolute_angle="left")

  trip = 0
  while True:
    here, there = points[trip % 2], points[(trip + 1) % 2]
    print(f"trip {trip + 1}: {'over' if trip % 2 == 0 else 'back'}")
    await carry(iswap, deck, plate, here, there, travel_z)
    trip += 1
    await asyncio.sleep(1.0)


if __name__ == "__main__":
  try:
    asyncio.run(main())
  except KeyboardInterrupt:
    pass
