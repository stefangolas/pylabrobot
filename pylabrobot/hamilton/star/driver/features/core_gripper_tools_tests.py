"""The CO-RE grip tools picked up and put back by a simulated STARlet's channels."""

import unittest
from typing import Any, Dict, List

from pylabrobot.resources.coordinate import Coordinate
from pylabrobot.resources.errors import HasTipError
from pylabrobot.resources.hamilton.core_grippers import HamiltonCoreGrippers
from pylabrobot.resources.tip_rack import TipRack
from pylabrobot.resources.tip_tracking import does_tip_tracking, set_tip_tracking
from pylabrobot.visualizer3D.demo import build_facility, star_of


class CoreGripperToolTests(unittest.IsolatedAsyncioTestCase):
  async def asyncSetUp(self) -> None:
    was = does_tip_tracking()
    set_tip_tracking(True)
    self.addCleanup(set_tip_tracking, was)
    self.star = star_of(build_facility())
    await self.star.setup()
    pipettes = self.star.pipettes
    assert pipettes is not None
    self.pipettes = pipettes
    self.holder = pipettes.core_gripper_holder()
    self.front, self.back = self.holder.front_tool, self.holder.back_tool
    self.sent: List[Dict[str, Any]] = []
    send = self.star.driver.send_command

    async def spy(*args: Any, **kwargs: Any):
      if kwargs.get("command") in ("ZT", "ZS"):
        self.sent.append(kwargs)
      return await send(*args, **kwargs)

    self.star.driver.send_command = spy  # type: ignore[method-assign]

  def wire(self, sent: Dict[str, Any], *keys: str) -> Dict[str, Any]:
    return {key: sent[key] for key in keys}

  async def test_the_tools_are_taken_where_legacy_takes_them_and_mounted(self):
    await self.pipettes.pick_up_core_gripper_tools(front_channel=7)
    # Legacy's own wire test, on the same deck: `C0ZT...xs07975xd0ya1250yb1070pa07pb08tp2350tz2250`.
    self.assertEqual(
      self.wire(self.sent[-1], "xs", "xd", "ya", "yb", "pa", "pb", "tp", "tz", "tt"),
      {
        "xs": "07975",
        "xd": "0",
        "ya": "1250",
        "yb": "1070",
        "pa": "07",
        "pb": "08",
        "tp": "2350",
        "tz": "2250",
        "tt": "14",
      },
    )
    self.assertEqual(self.pipettes.get_core_gripper_channels(), [6, 7])
    self.assertIs(self.pipettes.get_mounted_tool(6), self.back)
    self.assertIs(self.pipettes.get_mounted_tool(7), self.front)

  async def test_the_tools_go_back_exactly_where_they_were_parked(self):
    parked = {t.name: (t.location, t.rotation.z) for t in (self.front, self.back)}
    await self.pipettes.pick_up_core_gripper_tools(front_channel=7)
    front, back = self.front, self.back
    self.assertIsNot(front.parent, self.holder)
    await self.pipettes.return_core_gripper_tools()
    self.assertEqual(
      self.wire(self.sent[-1], "xs", "ya", "yb", "tp", "tz"),
      {"xs": "07975", "ya": "1250", "yb": "1070", "tp": "2150", "tz": "2050"},
    )
    self.assertEqual(self.pipettes.get_core_gripper_channels(), [])
    for tool in (front, back):
      self.assertIs(tool.parent, self.holder)
      self.assertEqual((tool.location, tool.rotation.z), parked[tool.name])

  async def test_the_block_puts_them_back(self):
    async with self.pipettes.core_gripper_tools(front_channel=3):
      self.assertEqual(self.pipettes.get_core_gripper_channels(), [2, 3])
    self.assertEqual(self.pipettes.get_core_gripper_channels(), [])

  async def test_a_channel_carrying_something_does_not_take_a_tool(self):
    rack = self.star.deck.get_resource("tips_0")
    assert isinstance(rack, TipRack)
    await self.pipettes.pick_up_tips([rack.get_item("A1")], use_channels=[7])
    with self.assertRaises(HasTipError):
      await self.pipettes.pick_up_core_gripper_tools(front_channel=7)
    self.assertEqual(self.sent, [])

  async def test_a_channel_carrying_a_tool_does_not_take_a_tip(self):
    await self.pipettes.pick_up_core_gripper_tools(front_channel=7)
    rack = self.star.deck.get_resource("tips_0")
    assert isinstance(rack, TipRack)
    with self.assertRaises(HasTipError):
      await self.pipettes.pick_up_tips([rack.get_item("A1")], use_channels=[7])

  async def test_the_front_channel_needs_one_behind_it(self):
    with self.assertRaises(ValueError):
      await self.pipettes.pick_up_core_gripper_tools(front_channel=0)

  async def test_offsets_move_the_channels_as_legacy_moves_them(self):
    await self.pipettes.pick_up_core_gripper_tools(
      front_channel=7,
      front_offset=Coordinate(1.0, 0.5, -2.0),
      back_offset=Coordinate(1.0, -0.5, -2.0),
    )
    self.assertEqual(
      self.wire(self.sent[-1], "xs", "ya", "yb", "tp", "tz"),
      {"xs": "07985", "ya": "1245", "yb": "1075", "tp": "2330", "tz": "2230"},
    )
    with self.assertRaises(ValueError):  # one X for both channels
      await self.pipettes.return_core_gripper_tools(
        front_offset=Coordinate(1, 0, 0), back_offset=Coordinate(2, 0, 0)
      )


class HolderTests(unittest.TestCase):
  def test_a_holder_saved_before_the_tools_x_was_stated_takes_them_on_its_own_x(self):
    holder = HamiltonCoreGrippers(
      "h",
      back_channel_y_center=30,
      front_channel_y_center=10,
      size_x=40,
      size_y=40,
      size_z=20,
      model="test_holder",
    )
    data = holder.serialize()
    del data["channel_x_center"]
    restored = HamiltonCoreGrippers.deserialize(data)
    assert isinstance(restored, HamiltonCoreGrippers)
    self.assertEqual(restored.channel_x_center, 0.0)


if __name__ == "__main__":
  unittest.main()
