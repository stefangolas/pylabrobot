"""The Inheco ODTC (On-Deck Thermal Cycler) as a deck resource, for `ExperimentalODTCBackend`."""

import os
from typing import Any, Dict, Optional

from pylabrobot.legacy.thermocycling.backend import ThermocyclerBackend
from pylabrobot.legacy.thermocycling.thermocycler import Thermocycler
from pylabrobot.resources.coordinate import Coordinate

# From Hamilton's model of the ODTC as it stands on the Multiflex carrier (ODTC.x; Inheco gives the
# bare unit as 156.5 x 248 x 124.3, Hamilton's includes its mounting): origin at the corner of its
# footprint, on its underside, +Y towards the rear.
ODTC_SIZE_X = 156.0
ODTC_SIZE_Y = 247.9
ODTC_SIZE_Z = 129.4

# An SBS plate centred on the thermal block's 96-hole grid (grid centre 78.0, 61.39), its bottom
# 86.5 above the ODTC's underside: Hamilton's plate site (MFX_CAR_ODTC_MTP.tml, 1_ODTC at Z 94.5 on
# the 7T carrier) less the carrier's 8 mm plate the ODTC stands on.
ODTC_PLATE_LOCATION = Coordinate(78.0 - 127.76 / 2, 61.39 - 85.48 / 2, 86.5)

# How far the heated cover slides (-Y) to close over the plate, as the model draws it: an estimate
# from Hamilton's geometry, not a measured stroke.
ODTC_COVER_STROKE = 101.0

_MODEL = os.path.join(
  os.path.dirname(__file__), "..", "..", "..", "inheco", "resource_model", "inheco_odtc.glb"
)


class InhecoODTC(Thermocycler):
  """An Inheco ODTC: holds one plate on its thermal block, under a sliding heated cover.

  The cover's state follows `open_lid` / `close_lid`; it is unknown until one of them is called,
  and drawn open until then.
  """

  def __init__(
    self,
    name: str,
    backend: ThermocyclerBackend,
    size_x: float = ODTC_SIZE_X,
    size_y: float = ODTC_SIZE_Y,
    size_z: float = ODTC_SIZE_Z,
    child_location: Coordinate = ODTC_PLATE_LOCATION,
    category: str = "thermocycler",
    model: Optional[str] = "inheco_odtc",
  ):
    super().__init__(
      name=name,
      size_x=size_x,
      size_y=size_y,
      size_z=size_z,
      backend=backend,
      child_location=child_location,
      category=category,
      model=model,
    )
    self.cover_open: Optional[bool] = None
    # The viewer's mesh declaration: the file, and the cover as a joint it slides.
    self.mesh = {
      "path": os.path.normpath(_MODEL),
      "units": "m",
      "up": "Z",
      # 40 mm/s: the stroke in about 2.5 s, a visual estimate.
      "joints": {
        "cover_slide": {"node": "heated_cover", "type": "prismatic", "axis": "y", "speed": 40.0}
      },
    }

  async def open_lid(self, **backend_kwargs):
    result = await super().open_lid(**backend_kwargs)
    self._set_cover(True)
    return result

  async def close_lid(self, **backend_kwargs):
    result = await super().close_lid(**backend_kwargs)
    self._set_cover(False)
    return result

  def _set_cover(self, is_open: bool) -> None:
    self.cover_open = is_open
    self._state_updated()

  def serialize_state(self) -> Dict[str, Any]:
    travel = 0.0 if self.cover_open in (None, True) else -ODTC_COVER_STROKE
    return {**super().serialize_state(), "cover_open": self.cover_open,
            "joints": {"cover_slide": travel}}

  def load_state(self, state: Dict[str, Any]) -> None:
    super().load_state(state)
    self.cover_open = state.get("cover_open")


def inheco_odtc(name: str, backend: ThermocyclerBackend) -> InhecoODTC:
  """Inheco ODTC 96 (On-Deck Thermal Cycler), e.g. with `ExperimentalODTCBackend(ip=...)`.

  Geometry from Hamilton's ODTC model and its NGS STAR carrier template (MFX_CAR_ODTC_MTP); a
  plate stands centred on the block, its bottom 86.5 above the ODTC's underside.
  """
  return InhecoODTC(name=name, backend=backend)
