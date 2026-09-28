"""Partial 96-head pick-ups from a Hamilton CO-RE 96 tip support.

A 96-head picks up tips with all 96 channels at once. To take only n columns, a rack's tips are
first ejected onto a tip support (`hamilton_96_tip_support`), which holds them higher than a rack
does. The head is then sent over the support shifted right by whole columns, so that only its
first n columns stand over tips and the rest of it hangs past the support, above the tips of
whatever stands next to it. Taking the support's columns from the right keeps the tips on the
head's first n columns: those work plate columns 1 to n, and carry the A1 / B2 cLLD sensor.

This is what pyhamilton's `TipSupportTracker` (Hamilton's NGS STAR methods) does through Venus's
reduced-pattern pick-up. Here the support's own spots are the record of what it holds.
"""

from typing import List, Optional, Sequence

from pylabrobot.hamilton.star.driver.features.head96 import Head96
from pylabrobot.resources.coordinate import Coordinate
from pylabrobot.resources.tip_rack import TipRack

COLUMNS, ROWS = 12, 8


def _occupancy(rack: TipRack) -> List[int]:
  """How many tips each of a 96 rack's columns holds, left to right."""
  spots = rack.get_all_items()
  return [sum(spots[c * ROWS + r].tip is not None for r in range(ROWS)) for c in range(COLUMNS)]


def right_end_full_columns(rack: TipRack) -> int:
  """How many full columns end a rack's tips on the right: the rightmost occupied column and the
  full ones next to it, counting left until a column is not full."""
  occupancy = _occupancy(rack)
  occupied = [c for c in range(COLUMNS) if occupancy[c]]
  if not occupied:
    return 0
  n = 0
  for c in range(occupied[-1], -1, -1):
    if occupancy[c] != ROWS:
      break
    n += 1
  return n


class CORE96TipSupport:
  """A tip support that the 96-head fills from `racks` and takes columns of tips from.

  Needs tip tracking on: the support's and the racks' spots are what it reads and updates.

  Args:
    head96: the 96-head.
    support: the tip support, e.g. `hamilton_96_tip_support(...)`.
    racks: the racks it refills from, first first. A rack keeps whatever the support gives back.
  """

  def __init__(self, head96: Head96, support: TipRack, racks: Sequence[TipRack]):
    self.head96 = head96
    self.support = support
    self.racks = list(racks)
    self.source: Optional[TipRack] = None  # the rack the support's tips came from

  async def pick_up_columns(self, num_columns: int) -> None:
    """Pick up `num_columns` full columns of tips onto the head's first `num_columns` columns,
    reloading the support from the racks first if it does not end in that many."""
    if not 1 <= num_columns <= COLUMNS:
      raise ValueError(f"num_columns must be between 1 and {COLUMNS}, is {num_columns}")
    if right_end_full_columns(self.support) < num_columns:
      await self.reload(num_columns)
    occupancy = _occupancy(self.support)
    rightmost = max(c for c in range(COLUMNS) if occupancy[c])
    first = rightmost - num_columns + 1
    pitch = self.head96.configuration.channel_pitch
    await self.head96.pick_up_tips(self.support, offset=Coordinate(first * pitch, 0, 0))

  async def reload(self, num_columns: int) -> None:
    """Give the support's tips back to their rack, then fill it from the first rack that ends in
    at least `num_columns` full columns.

    Raises:
      ValueError: If no rack does, or the support holds tips that came from no known rack.
    """
    rack = next((r for r in self.racks if right_end_full_columns(r) >= num_columns), None)
    if rack is None:
      raise ValueError(f"no rack ends in {num_columns} full columns to refill the tip support from")
    if self.source is None and any(_occupancy(self.support)):
      raise ValueError("the tip support holds tips from no known rack; empty it first")
    if self.source is not None and any(_occupancy(self.support)):
      await self.head96.pick_up_tips(self.support)
      await self.head96.drop_tips(self.source)
    await self.head96.pick_up_tips(rack)
    await self.head96.drop_tips(self.support)
    self.source = rack
