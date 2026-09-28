"""Hamilton lids."""

from pylabrobot.resources.lid import Lid


def hamilton_pcr_comfort_lid(name: str) -> Lid:
  """Hamilton PCR ComfortLid, cat. no.: 814300, for plates in the Inheco ODTC.

  From Hamilton's definitions Ham_1_NB_Lid_ODTC_V1.0 and V1.1 (NGS STAR labware; same outline):
  127.5 x 85.3 at its base, 8.5 tall, stacking height 6.7: on a plate it adds 6.7, so it overlaps
  the plate by 1.8.
  """
  return Lid(
    name=name,
    size_x=127.5,
    size_y=85.3,
    size_z=8.5,
    nesting_z_height=8.5 - 6.7,
    model=hamilton_pcr_comfort_lid.__name__,
  )
