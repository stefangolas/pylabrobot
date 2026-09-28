"""Partial 96-head pick-ups from a CO-RE 96 tip support, on a simulated STAR."""

import unittest
from typing import List, Optional, cast

from pylabrobot.hamilton.star.device import RECORDING_STAR
from pylabrobot.hamilton.star.driver.features.head96 import Head96
from pylabrobot.hamilton.star.driver.simulator import STARSimulationDriver
from pylabrobot.hamilton.star.tip_support import CORE96TipSupport, right_end_full_columns
from pylabrobot.resources import set_tip_tracking
from pylabrobot.resources.hamilton import (
  STARDeck,
  TIP_CAR_480BC_A00,
  hamilton_96_tip_support,
  hamilton_96_tiprack_300uL_filter,
  hamilton_tip_300uL_filter,
)
from pylabrobot.resources.tip_rack import TipRack


def columns(rack: TipRack) -> List[int]:
  spots = rack.get_all_items()
  return [sum(spots[c * 8 + r].tip is not None for r in range(8)) for c in range(12)]


class TipSupportTests(unittest.IsolatedAsyncioTestCase):
  async def asyncSetUp(self):
    set_tip_tracking(True)
    self.addCleanup(set_tip_tracking, False)
    self.deck = STARDeck()
    self.driver = STARSimulationDriver(deck=self.deck, declared_configuration_json=RECORDING_STAR)
    await self.driver.setup()
    self.head = cast(Head96, self.driver.head96)
    carrier = TIP_CAR_480BC_A00("tip_carrier")
    carrier[4] = self.support_rack = hamilton_96_tip_support(
      "support", "300uL", hamilton_tip_300uL_filter, core_ii=True
    )
    carrier[3] = self.rack_1 = hamilton_96_tiprack_300uL_filter("rack_1")
    carrier[2] = self.rack_2 = hamilton_96_tiprack_300uL_filter("rack_2")
    self.deck.assign_child_resource(carrier, track=18)
    self.support = CORE96TipSupport(self.head, self.support_rack, [self.rack_1, self.rack_2])
    self.sent: List[str] = []
    log = self.driver._log_exchange

    def recorded(written: str, read: Optional[str]) -> None:
      if written[:4] in ("C0EP", "C0ER"):
        self.sent.append(written)
      log(written, read)

    self.driver._log_exchange = recorded  # type: ignore[method-assign]

  def head_columns(self) -> List[int]:
    shafts = self.head.resource.get_all_items()
    return [sum(shafts[c * 8 + r].has_tip() for r in range(8)) for c in range(12)]

  async def discard(self):
    await self.head.drop_tips(self.deck.get_trash_area96())

  async def test_the_first_pick_up_fills_the_support_and_takes_its_right_columns(self):
    await self.support.pick_up_columns(2)
    self.assertEqual(columns(self.rack_1), [0] * 12)
    self.assertEqual(columns(self.support_rack), [8] * 10 + [0, 0])
    self.assertEqual(self.head_columns(), [8, 8] + [0] * 10)
    # a full rack onto the support, then the head shifted 10 columns right
    a1 = self.support_rack.get_item("A1").get_location_wrt(self.deck, "c", "c", "b")
    self.assertIn(f"C0EPxs{round((a1.x + 90) * 10):05}", self.sent[-1])

  async def test_columns_are_taken_right_to_left(self):
    for n, left in ((2, [8] * 10 + [0] * 2), (3, [8] * 7 + [0] * 5), (7, [0] * 12)):
      with self.subTest(n=n):
        await self.support.pick_up_columns(n)
        self.assertEqual(self.head_columns(), [8] * n + [0] * (12 - n))
        self.assertEqual(columns(self.support_rack), left)
        await self.discard()

  async def test_too_few_columns_left_go_back_to_their_rack(self):
    await self.support.pick_up_columns(11)
    await self.discard()
    await self.support.pick_up_columns(2)  # one column left: back to rack_1, then rack_2 in
    self.assertEqual(columns(self.rack_1), [8] + [0] * 11)
    self.assertEqual(columns(self.rack_2), [0] * 12)
    self.assertEqual(columns(self.support_rack), [8] * 10 + [0, 0])
    self.assertIs(self.support.source, self.rack_2)

  async def test_a_rack_used_from_the_left_is_taken_from_the_right(self):
    """Racks the 8 channels have been taking columns from, from the left, still fill the support."""
    for spot in self.rack_1.get_all_items()[:24]:
      spot.unassign_tip()
    self.assertEqual(right_end_full_columns(self.rack_1), 9)
    await self.support.pick_up_columns(4)
    self.assertEqual(columns(self.support_rack), [0] * 3 + [8] * 5 + [0] * 4)
    self.assertEqual(self.head_columns(), [8] * 4 + [0] * 8)

  async def test_no_rack_left_is_refused(self):
    for rack in (self.rack_1, self.rack_2):
      for spot in rack.get_all_items()[:88]:
        spot.unassign_tip()
    with self.assertRaises(ValueError):
      await self.support.pick_up_columns(2)
    self.assertEqual(self.sent, [])


if __name__ == "__main__":
  unittest.main()
