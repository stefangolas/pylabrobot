"""Moving plates with the CO-RE grip tools, on a simulated STAR."""

import unittest
from typing import List, Optional, cast

from pylabrobot.hamilton.star.device import RECORDING_STAR
from pylabrobot.hamilton.star.driver.features.core_gripper import COREGripper
from pylabrobot.hamilton.star.driver.features.pipettes import Pipettes
from pylabrobot.hamilton.star.driver.simulator import STARSimulationDriver
from pylabrobot.resources import Coordinate
from pylabrobot.resources.alpaqua import alpaqua_96_plateadapter_magnum_ex
from pylabrobot.resources.hamilton import STARDeck
from pylabrobot.resources.hamilton.mfx_carriers import (
  hamilton_mfx_carrier_L5_2MTP_MIDI_2DWP_HP_tabbed,
)
from pylabrobot.resources.thermo_fisher import thermo_TS_abgene_96_wellplate_800uL_Vb


class COREGripperTests(unittest.IsolatedAsyncioTestCase):
  async def asyncSetUp(self):
    self.deck = STARDeck()
    self.driver = STARSimulationDriver(deck=self.deck, declared_configuration_json=RECORDING_STAR)
    await self.driver.setup()
    self.carrier = hamilton_mfx_carrier_L5_2MTP_MIDI_2DWP_HP_tabbed("carrier")
    self.magnet = alpaqua_96_plateadapter_magnum_ex("magnet")
    self.carrier.sites[0].assign_child_resource(self.magnet)
    self.midi = thermo_TS_abgene_96_wellplate_800uL_Vb("midi")
    self.carrier.sites[2].assign_child_resource(self.midi)
    self.deck.assign_child_resource(self.carrier, track=35)
    self.pipettes = cast(Pipettes, self.driver.pipettes)
    self.gripper = COREGripper(self.pipettes)
    self.sent: List[str] = []
    log = self.driver._log_exchange

    def recorded(written: str, read: Optional[str]) -> None:
      if written[:4] in ("C0ZT", "C0ZS", "C0ZP", "C0ZM", "C0ZR"):
        self.sent.append(written[:4])
      log(written, read)

    self.driver._log_exchange = recorded  # type: ignore[method-assign]

  async def test_a_midi_plate_onto_the_magnet(self):
    """As KAPA HyperPlus moves it: off the MIDI nest, onto the Magnum EX in the front nest."""
    before = self.midi.get_well("A1").get_location_wrt(self.deck, "c", "c", "b")
    await self.gripper.pick_up_resource(self.midi)
    self.assertEqual(self.sent, ["C0ZT", "C0ZP"])
    self.assertIsNone(self.carrier.sites[2].resource)
    await self.gripper.drop_resource(self.magnet, return_tools=True)
    self.assertEqual(self.sent, ["C0ZT", "C0ZP", "C0ZR", "C0ZS"])
    self.assertIs(self.midi.parent, self.magnet)
    after = self.midi.get_well("A1").get_location_wrt(self.deck, "c", "c", "b")
    # two nests (192 mm) forward, less the 0.06 the magnet moves it to put its wells over the rings
    self.assertAlmostEqual(before.y - after.y, 192.0 - 0.06, places=6)
    self.assertAlmostEqual(self.midi.get_location_wrt(self.carrier).z, 82.4 + 29.21, places=6)

  async def test_while_held_it_rides_with_the_channels(self):
    await self.gripper.pick_up_resource(self.midi)
    shaft = self.pipettes.shaft(self.pipettes.get_core_gripper_channels()[-1])
    self.assertIs(self.midi.parent, shaft)

  async def test_left_of_the_arms_reach_is_refused_before_anything_moves(self):
    """The channels travel with the arm: a plate left of its X travel (the NGS STAR decks' ODTC,
    left of track 1) is not reached."""
    far_left = thermo_TS_abgene_96_wellplate_800uL_Vb("far_left")
    self.deck.assign_child_resource(far_left, location=Coordinate(-90.0, 200.0, 180.0))
    with self.assertRaises(ValueError):
      await self.gripper.pick_up_resource(far_left)
    self.assertEqual(self.sent, [])

  async def test_every_axis_is_checked_before_anything_moves(self):
    """Y: the front tool stands in front of the plate, so a plate at the front edge of the channels'
    band is not reached. Z: the grip line hangs 22 mm below the stop disc, whose window tops out at
    334.7, so a grip line higher than 312.7 is not reached."""
    cases = {
      "y": Coordinate(500.0, 0.0, 180.0),
      "z": Coordinate(500.0, 200.0, 320.0),
    }
    for axis, location in cases.items():
      with self.subTest(axis=axis):
        plate = thermo_TS_abgene_96_wellplate_800uL_Vb(f"plate_{axis}")
        self.deck.assign_child_resource(plate, location=location, ignore_collision=True)
        with self.assertRaises(ValueError):
          await self.gripper.pick_up_resource(plate)
        self.assertEqual(self.sent, [])

  async def test_nothing_held_cannot_be_dropped(self):
    with self.assertRaises(RuntimeError):
      await self.gripper.drop_resource(self.magnet)


if __name__ == "__main__":
  unittest.main()
