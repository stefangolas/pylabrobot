from typing import Dict, Optional

from pylabrobot.resources import Coordinate, ResourceHolder

from .control_box import InhecoTECControlBox
from .temperature_controller import InhecoTemperatureController


class InhecoCPAC(ResourceHolder, InhecoTemperatureController):
  """Inheco CPAC: a temperature-controlled plate holder addressed by index on a control box."""

  def __init__(
    self,
    index: int,
    name: str,
    size_x: float,
    size_y: float,
    size_z: float,
    control_box: InhecoTECControlBox,
    child_location: Coordinate,
    category: str = "temperature_controller",
    model: Optional[str] = None,
  ):
    ResourceHolder.__init__(
      self,
      name=name,
      size_x=size_x,
      size_y=size_y,
      size_z=size_z,
      child_location=child_location,
      category=category,
      model=model,
    )
    InhecoTemperatureController.__init__(self, index=index, interface=control_box)


# The CPAC Ultraflat (7000166, 7000190, 7000165), from Inheco's dimensioned drawing (CPAC brochure,
# "Drawings CPAC Ultraflat"): 129 long overall, the thermal adapter 89 wide, 80 from its feet to
# the top of the thermal adapter. The contact surface under the adapter is 113 x 77.
CPAC_ULTRAFLAT_SIZE_X = 129.0
CPAC_ULTRAFLAT_SIZE_Y = 89.0
CPAC_ULTRAFLAT_HEIGHT = 80.0

# Where a plate's bottom rests, above the CPAC's feet, for each thermal adapter. Plates sit in a
# shaped adapter, their wells in its pockets and their skirt around it, so below the adapter's top.
CPAC_ULTRAFLAT_PLATE_SEAT: Dict[str, float] = {
  # PLR's earlier measurement; the adapter it was measured with is not recorded.
  "flat": 77.0,
  # Abgene 0.8 mL MIDI (AB-0765/AB-0859) adapter 3200376, and the low-profile 96-well PCR adapter
  # 3200203 (Bio-Rad Hard-Shell): from Hamilton's NGS STAR layouts, where these plates stand on a
  # CPAC on Hamilton's 10 mm bracket at 91.5 and 92.8 above the carrier's bottom (plate at 8).
  "abgene_midi": 73.5,
  "pcr_low_profile": 74.8,
  # Hamilton's 2 mL tube block (`hamilton_cpac_tube_block_2mL`), its bottom where Hamilton puts it:
  # the catalogue's "CPAC 2mL" site 102.6 above the carrier's bottom, which is also where Hamilton's
  # models stack it (10 mm bracket on the 8 mm plate, then the CPAC). No protocol uses the block,
  # so nothing has corrected it as the plate seats above were corrected.
  "tubes_2mL": 84.6,
}


def inheco_cpac_ultraflat(
  name: str, control_box: InhecoTECControlBox, index: int, adapter: str = "flat"
) -> InhecoCPAC:
  """Inheco CPAC Ultraflat
  7000166, 7000190, 7000165

  `adapter` is the thermal adapter on top, which sets how deep a plate sits: one of
  `CPAC_ULTRAFLAT_PLATE_SEAT`. A plate stands centred on the unit.

  https://www.inheco.com/data/pdf/cpac-brochure-1013-1032-34.pdf (now gone; archived at
  web.archive.org/web/20220116105940/https://www.inheco.com/data/pdf/cpac-brochure-1013-1032-34.pdf)

  Example:
    >>> from pylabrobot.inheco import inheco_cpac_ultraflat
    >>> await box.setup()
    >>> cpac = inheco_cpac_ultraflat("cpac", control_box=box, index=1)
    >>> await cpac.set_temperature(37.0)
    >>> await cpac.request_current_temperature()
    37.0
  """
  if adapter not in CPAC_ULTRAFLAT_PLATE_SEAT:
    known = sorted(CPAC_ULTRAFLAT_PLATE_SEAT)
    raise ValueError(f"unknown CPAC adapter {adapter!r}; one of {known}")

  return InhecoCPAC(
    name=name,
    control_box=control_box,
    index=index,
    size_x=CPAC_ULTRAFLAT_SIZE_X,
    size_y=CPAC_ULTRAFLAT_SIZE_Y,
    size_z=CPAC_ULTRAFLAT_HEIGHT,
    # an SBS plate centred on the unit
    child_location=Coordinate(
      x=(CPAC_ULTRAFLAT_SIZE_X - 127.76) / 2,
      y=(CPAC_ULTRAFLAT_SIZE_Y - 85.48) / 2,
      z=CPAC_ULTRAFLAT_PLATE_SEAT[adapter],
    ),
    model=inheco_cpac_ultraflat.__name__,
  )
