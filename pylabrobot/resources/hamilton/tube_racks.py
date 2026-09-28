"""Tube adapters from Hamilton's NGS STAR labware definitions."""

from typing import Dict

from pylabrobot.resources.coordinate import Coordinate
from pylabrobot.resources.resource_holder import ResourceHolder
from pylabrobot.resources.tube_rack import TubeRack

# Both adapters: 4 x 6 positions at 15 mm, A1 25.5 from the left and 20.5 from the back of a
# 127 x 86 footprint, 32 tall (AdapterEppendorfTubePos24.rck, AdapterEppendorfTubePos24_GEMX.rck).
# Here on the SBS 127.76 x 85.48 footprint, the grid kept on the same centre.
_A1_X = 25.5 + (127.76 - 127.0) / 2
_A1_Y = (86.0 - 20.5) - (86.0 - 85.48) / 2


def _adapter(name: str, model: str, seats: Dict[str, float], hole: float) -> TubeRack:
  """A 4 x 6 adapter whose position `key` holds a tube standing at `seats[key]`."""
  holders: Dict[str, ResourceHolder] = {}
  for column in range(6):  # column-major, as create_ordered_items_2d orders items
    for row, letter in enumerate("ABCD"):
      key = f"{letter}{column + 1}"
      holder = ResourceHolder(
        name=f"{name}_{key}", size_x=hole, size_y=hole, size_z=32.0 - seats[key]
      )
      holder.location = Coordinate(
        _A1_X + 15.0 * column - hole / 2, _A1_Y - 15.0 * row - hole / 2, seats[key]
      )
      holders[key] = holder
  return TubeRack(
    name=name, size_x=127.76, size_y=85.48, size_z=32.0, ordered_items=holders, model=model
  )


def hamilton_24_tuberack_eppendorf_1_5mL_adapter(name: str) -> TubeRack:
  """24-position adapter for 1.5 mL Eppendorf tubes (NGS STAR: Avenio, QIAseq, Oxford Nanopore).

  Hamilton's definition 'AdapterEppendorfTubePos24' ("Adapter for eppendorf tube with 24
  positions"; its maker is not stated). A tube's floor is 5.1 above the adapter's bottom
  (vial_vbottom.ctr); the tube stands 1.3 lower, on its own bottom (`eppendorf_tube_1500uL_Vb`).
  Each position is sized to that tube (9.85 across) so that one stands centred.
  """
  seats = {f"{r}{c}": 5.1 - 1.3 for r in "ABCD" for c in range(1, 7)}
  return _adapter(name, hamilton_24_tuberack_eppendorf_1_5mL_adapter.__name__, seats, hole=9.85)


def hamilton_24_tuberack_gemx_adapter(name: str) -> TubeRack:
  """24-position tube adapter of the 10x Genomics Chromium GEM-X protocol: Sarstedt 0.5 mL V-bottom
  tubes in columns 1, 2 and 4, Sarstedt 2.0 mL skirted tubes in columns 3, 5 and 6.

  Hamilton's definition 'AdapterEppendorfTubePos24_GEMX' ("Tube Adapter (24 Positions)"): the grid
  of `hamilton_24_tuberack_eppendorf_1_5mL_adapter`, a 0.5 mL tube's floor 2.5 and a 2.0 mL skirted
  tube's 10.7 above the adapter's bottom. PLR has no Sarstedt tube definitions, so each position's
  seat is that floor and its size the definition's 8.4 mm hole.
  """
  seats = {f"{r}{c}": (10.7 if c in (3, 5, 6) else 2.5) for r in "ABCD" for c in range(1, 7)}
  return _adapter(name, hamilton_24_tuberack_gemx_adapter.__name__, seats, hole=8.4)
