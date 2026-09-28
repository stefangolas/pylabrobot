"""Roche reagent reservoirs."""

from pylabrobot.resources.hamilton.troughs import (
  reservoir_20mL_height_from_volume,
  reservoir_20mL_volume_from_height,
)
from pylabrobot.resources.trough import Trough, TroughBottomType


def roche_1_trough_20mL_Vb(name: str) -> Trough:
  """Roche 20 mL reagent reservoir, as supplied with Roche's NGS kits (Hamilton's definition
  'Roche_20mL_reservoir', NGS STAR Oxford Nanopore and 10x Genomics protocols).

  20 x 89.9 x 38, eight positions 9 apart. Its floor is at its bottom and the container is 37.5
  deep (roche_20ml_reservoir.ctr): about 26.5 mL to the top.
  """
  return Trough(
    name=name,
    size_x=20.0,
    size_y=89.9,
    size_z=38.0,
    material_z_thickness=0.0,
    max_volume=reservoir_20mL_volume_from_height(37.5),
    model=roche_1_trough_20mL_Vb.__name__,
    bottom_type=TroughBottomType.V,
    compute_volume_from_height=reservoir_20mL_volume_from_height,
    compute_height_from_volume=reservoir_20mL_height_from_volume,
  )
