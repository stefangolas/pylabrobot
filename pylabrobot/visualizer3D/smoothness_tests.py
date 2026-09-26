"""Runs drawn as smooth motion, checked with a headless page (`smoothness.py`), no browser.

Each scenario runs a simulated STAR under the viewer with motion attached, watched by the headless
page, and is held to all of it: nothing jumps; nothing a motion does not move moves while it plays;
nothing moves outside a motion; every model update finds the page already where it says; and at the
end everything is where the model has it. The last tests check that the watching catches what it is
for.
"""

import asyncio
import unittest
from typing import Any, Awaitable, Callable, Tuple

from pylabrobot.resources.coordinate import Coordinate
from pylabrobot.resources.corning.plates import cor_96_wellplate_360uL_Fb_lid
from pylabrobot.resources.plate import Plate
from pylabrobot.resources.tip_rack import TipRack
from pylabrobot.resources.tip_tracking import does_tip_tracking, set_tip_tracking
from pylabrobot.visualizer3D import iswap_demo as grip
from pylabrobot.visualizer3D.demo import build_facility, fill, star_of
from pylabrobot.visualizer3D.server import Viewer3D
from pylabrobot.visualizer3D.server_tests import free_ports, track_volumes
from pylabrobot.visualizer3D.smoothness import NODE, Report, assert_smooth, watched

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

  async def smooth(
    self, scenario: Callable[[Any], Awaitable[None]], *, lid: bool = False, speed: float = 8.0
  ) -> Report:
    """Run `scenario(star)` watched, and hold it to every check, the model's end state included."""
    facility, star, viewer = await self.run_star(lid=lid)
    async with watched(viewer, speed=speed) as report:
      await scenario(star)
      await asyncio.sleep(0.3)
    self.assertGreater(report.motions, 0, "nothing was acted out")
    assert_smooth(report, model=facility)
    return report

  # -- channels ----------------------------------------------------------------------------------

  async def test_a_column_is_picked_up_aspirated_from_and_put_back(self):
    async def scenario(star: Any) -> None:
      rack, source = star.deck.get_resource("tips_0"), star.deck.get_resource("source_0")
      fill(source, 300.0)
      tips = [rack.get_item(f"{row}1") for row in ROWS]
      await star.pipettes.pick_up_tips(tips)
      await star.pipettes.aspirate([source.get_item(f"{row}1") for row in ROWS], [50.0] * 8)
      await star.pipettes.drop_tips(tips)

    await self.smooth(scenario, speed=4.0)

  async def test_one_channel_picks_up_and_puts_back(self):
    async def scenario(star: Any) -> None:
      spot = star.deck.get_resource("tips_0").get_item("D5")
      await star.pipettes.pick_up_tips([spot], use_channels=[3])
      await star.pipettes.drop_tips([spot], use_channels=[3])

    await self.smooth(scenario)

  async def test_scattered_channels_push_the_others_along_the_rail(self):
    async def scenario(star: Any) -> None:
      rack = star.deck.get_resource("tips_0")
      spots = [rack.get_item(well) for well in ("A6", "C6", "F6")]
      await star.pipettes.pick_up_tips(spots, use_channels=[0, 2, 5])
      await star.pipettes.drop_tips(spots, use_channels=[0, 2, 5])

    await self.smooth(scenario)

  async def test_one_channel_aspirates_along_a_row(self):
    async def scenario(star: Any) -> None:
      rack, source = star.deck.get_resource("tips_0"), star.deck.get_resource("source_0")
      fill(source, 300.0)
      await star.pipettes.pick_up_tips([rack.get_item("A7")])
      for column in (1, 4, 8, 12):
        await star.pipettes.aspirate([source.get_item(f"B{column}")], [20.0])
      await star.pipettes.drop_tips([rack.get_item("A7")])

    await self.smooth(scenario)

  async def test_the_channels_and_the_arm_move_on_their_own(self):
    async def scenario(star: Any) -> None:
      low, high = star.x_arm.configuration.x_range
      await star.pipettes.move_to_y_positions({0: 400.0}, make_space=True)
      await star.x_arm.move_to_x_position(round(low + (high - low) * 0.7, 1))
      await star.pipettes.move_to_y_positions({7: 120.0}, make_space=True)
      await star.x_arm.move_to_x_position(round(low + (high - low) * 0.2, 1))

    await self.smooth(scenario)

  # -- 96-head -----------------------------------------------------------------------------------

  async def test_the_96_head_picks_up_a_rack_and_puts_it_back(self):
    async def scenario(star: Any) -> None:
      head = star.driver.arms[0].head96
      rack = star.deck.get_resource("tips_0")
      await head.pick_up_tips(rack)
      await head.drop_tips(rack)

    report = await self.smooth(scenario)
    self.assertFalse(report.handovers)

  async def test_the_96_head_moves_on_its_own(self):
    async def scenario(star: Any) -> None:
      head = star.driver.arms[0].head96
      y = await head.request_y_position()
      await head.move_to_y_position(round(y - 150.0, 1))
      z = await head.request_z_position()
      await head.move_stop_disc_to_z_position(round(z - 40.0, 1))
      await head.move_to_safe_z()

    await self.smooth(scenario)

  # -- iSWAP -------------------------------------------------------------------------------------

  async def test_the_iswap_turns_its_joints(self):
    async def scenario(star: Any) -> None:
      iswap = star.iswap
      await iswap.make_space()
      parked = await iswap.elbow_request_y_position()
      await iswap.elbow_move_to_y_position(parked - 200.0)
      for elbow, wrist in (
        ("front", "front"),
        ("left", "front"),
        ("front", "left"),
        ("right", "right"),
      ):
        try:
          await iswap.rotate_to_angles(elbow_absolute_angle=elbow, gripper_absolute_angle=wrist)
        except ValueError:
          pass  # a pose the guards refuse is not drawn either

    await self.smooth(scenario)

  async def test_the_iswap_opens_and_closes_its_jaws(self):
    async def scenario(star: Any) -> None:
      iswap = star.iswap
      await iswap.gripper_open()
      await iswap.gripper_move_to_jaw_position(90.0)
      await iswap.gripper_move_to_jaw_position(120.0)

    await self.smooth(scenario)

  async def test_the_iswap_carries_a_plate_and_its_lid(self):
    async def scenario(star: Any) -> None:
      deck, iswap = star.deck, star.iswap
      plate = deck.get_resource("source_1")
      lid = plate.lid
      start, other = plate.parent, deck.get_resource("destination_carrier").children[1]
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

    report = await self.smooth(scenario, lid=True)
    self.assertIn("source_1", report.carried)

  # -- the watching catches what it is for -------------------------------------------------------

  async def test_something_put_elsewhere_with_no_motion_is_a_snap_a_jump_and_an_arrival(self):
    _, star, viewer = await self.run_star()
    plate = star.deck.get_resource("source_2")
    async with watched(viewer) as report:
      await asyncio.sleep(0.3)
      plate.location = plate.location + Coordinate(0, 0, 200)
      await asyncio.sleep(0.3)
    self.assertIn(plate.name, {s["name"] for s in report.snaps})
    self.assertIn(plate.name, {j["name"] for j in report.jumps})
    # The update that moved it found the page elsewhere.
    self.assertIn(plate.name, {a["name"] for a in report.arrivals})
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

  async def test_a_page_left_behind_the_model_ends_away_from_it(self):
    """The model moved while nobody was drawing it: the page never heard, and ends elsewhere."""
    facility, star, viewer = await self.run_star()
    plate = star.deck.get_resource("source_2")
    async with watched(viewer) as report:
      await asyncio.sleep(0.2)
    plate.location = plate.location + Coordinate(0, 0, 50)
    with self.assertRaises(AssertionError) as raised:
      assert_smooth(report, model=facility)
    self.assertIn("ending away from the model", str(raised.exception))


if __name__ == "__main__":
  unittest.main()
