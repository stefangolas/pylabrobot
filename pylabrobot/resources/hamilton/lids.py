"""Hamilton lids."""

from pylabrobot.resources.lid import Lid


def hamilton_pcr_comfort_lid(name: str) -> Lid:
  """Hamilton PCR ComfortLid, cat. no.: 814300, for plates in the Inheco ODTC.

  From Hamilton's definitions Ham_1_NB_Lid_ODTC_V1.0 and V1.1 (NGS STAR labware; same outline):
  127.5 x 85.3 at its base, 8.5 tall. On a plate in the ODTC, Hamilton's carrier template
  (MFX_CAR_ODTC_MTP) puts the lid's bottom 12.0 above the plate's (sites 1_ODTC at 94.5, 2_ODTC_LID
  at 106.5): on a 16.06 mm Hard-Shell 96 it overlaps the plate by 4.06. (The definitions' stacking
  height, 6.7, is lid on lid.)
  """
  return Lid(
    name=name,
    size_x=127.5,
    size_y=85.3,
    size_z=8.5,
    nesting_z_height=16.06 - 12.0,
    model=hamilton_pcr_comfort_lid.__name__,
  )
