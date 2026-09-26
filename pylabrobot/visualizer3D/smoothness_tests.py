"""Runs drawn as smooth motion, checked with a headless page (`smoothness.py`), no browser.

Each scenario runs a simulated STAR under the viewer with motion attached, watched by the headless
page: nothing may jump, nothing a motion does not move may move while it plays, and nothing may
move outside a motion at all. The last tests check that the watching catches each of those.
"""

import asyncio
import unittest
from typing import Any, Tuple

from pylabrobot.resources.coordinate import Coordinate
from pylabrobot.resources.corning.plates import cor_96_wellplate_360uL_Fb_lid
from pylabrobot.resources.plate import Plate
from pylabrobot.resources.tip_rack import TipRack
from pylabrobot.resources.tip_tracking import does_tip_tracking, set_tip_tracking
from pylabrobot.visualizer3D import iswap_demo
from pylabrobot.visualizer3D.demo import build_facility, fill, star_of
from pylabrobot.visualizer3D.server import Viewer3D
from pylabrobot.visualizer3D.server_tests import free_ports, track_volumes
from pylabrobot.visualizer3D.smoothness import NODE, assert_smooth, watched

ROWS = "ABCDEFGH"


@unittest.skipUnless(NODE, "the headless page runs in Node")
class SmoothnessTests(unittest.IsolatedAsyncioTestCase):
  async def run_star(self, lid: bool = False) -> Tuple[Any, Any, Viewer3D]:
    track_volumes(self)
    was_tracking = does_tip_tracking()
    set_tip_tracking(True)
    self.addCleanup(set_tip_tracking, was_tracking)
    facility = build_facility()
    star = star_of(facility)
    if lid:
      star.deck.get_resource("destination_1").unassign()
      plate = star.deck.get_resource("source_1")
      assert isinstance(plate, Plate)
      plate.assign_child_resource(cor_96_wellplate_360uL_Fb_lid(name="source_1_lid"))
    await star.setup()
    fs_port, ws_port = free_ports(2)
    viewer = Viewer3D(facility, open_browser=False, fs_port=fs_port, ws_port=ws_port)
    await viewer.start()
    self.addAsyncCleanup(viewer.stop)
    viewer.attach_motion(star.driver)
    return facility, star, viewer

  async def test_a_column_is_picked_up_aspirated_from_and_put_back_smoothly(self):
    _, star, viewer = await self.run_star()
    rack = star.deck.get_resource("tips_0")
    source = star.deck.get_resource("source_0")
    assert isinstance(rack, TipRack) and isinstance(source, Plate)
    fill(source, 300.0)
    tips = [rack.get_item(f"{row}1") for row in ROWS]
    async with watched(viewer) as report:
      await star.pipettes.pick_up_tips(tips)
      await star.pipettes.aspirate([source.get_item(f"{row}1") for row in ROWS], [50.0] * 8)
      await star.pipettes.drop_tips(tips)
      await asyncio.sleep(0.3)
    self.assertGreaterEqual(report.motions, 3)
    assert_smooth(report)

  async def test_the_iswap_carries_a_plate_and_its_lid_smoothly(self):
    _, star, viewer = await self.run_star(lid=True)
    deck, iswap = star.deck, star.iswap
    plate = deck.get_resource("source_1")
    lid = plate.lid
    start, other = plate.parent, deck.get_resource("destination_carrier").children[1]
    grip = iswap_demo
    async with watched(viewer, speed=8) as report:
      await iswap.make_space()
      parked = await iswap.elbow_request_y_position()
      travel = grip.grip_centre(iswap, deck).z
      await iswap.elbow_move_to_y_position(parked - 200.0)
      await iswap.rotate_to_angles(elbow_absolute_angle="front", gripper_absolute_angle="left")
      width, lid_width = plate.get_size_y(), lid.get_size_y()
      for what, here, there in (
        (width, grip.plate_grip(start, plate, deck), grip.plate_grip(other, plate, deck)),
        (
          lid_width,
          grip.lid_grip_on_plate(other, plate, lid, deck),
          grip.lid_grip_on_site(start, deck),
        ),
        (
          lid_width,
          grip.lid_grip_on_site(start, deck),
          grip.lid_grip_on_plate(other, plate, lid, deck),
        ),
        (width, grip.plate_grip(other, plate, deck), grip.plate_grip(start, plate, deck)),
      ):
        await grip.carry(iswap, deck, what, here, there, travel)
      await asyncio.sleep(0.3)
    self.assertGreaterEqual(report.motions, 20)
    assert_smooth(report)

  # -- the watching catches what it is for ---------------------------------------------------------

  async def test_something_put_elsewhere_with_no_motion_is_a_snap_and_a_jump(self):
    _, star, viewer = await self.run_star()
    plate = star.deck.get_resource("source_2")
    async with watched(viewer) as report:
      await asyncio.sleep(0.3)
      plate.location = plate.location + Coordinate(0, 0, 200)
      await asyncio.sleep(0.3)
    self.assertIn(plate.name, {s["name"] for s in report.snaps})
    self.assertIn(plate.name, {j["name"] for j in report.jumps})
    with self.assertRaises(AssertionError):
      assert_smooth(report)

  async def test_something_a_motion_does_not_move_moving_during_it_is_a_stray(self):
    _, star, viewer = await self.run_star()
    rack = star.deck.get_resource("tips_0")
    plate = star.deck.get_resource("source_2")
    assert isinstance(rack, TipRack)

    async def nudge() -> None:
      await asyncio.sleep(0.2)
      plate.location = plate.location + Coordinate(0, 0, 3)

    async with watched(viewer) as report:
      await asyncio.gather(star.pipettes.pick_up_tips([rack.get_item("A1")]), nudge())
      await asyncio.sleep(0.3)
    self.assertIn(plate.name, {s["name"] for s in report.strays})


if __name__ == "__main__":
  unittest.main()
