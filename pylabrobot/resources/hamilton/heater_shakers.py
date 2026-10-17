"""Hamilton Heater Shaker (HHS) units and their nests, as they stand on a Multiflex carrier.

A Heater Shaker is a device with an exchangeable nest on top; a plate stands in the nest. In PLR
that is three resources, each placing the next through its own `child_location`:

  MFX shaker carrier slot -> HamiltonHeaterShaker -> nest (PlateHolder) -> plate

For flat MTP nests, Hamilton raises the unit on a 29 mm riser, one more resource under it:

  MFX shaker carrier slot -> riser -> HamiltonHeaterShaker -> flat MTP nest -> plate

Sources, and how each number was found:
  - Hamilton's Multiflex Carrier Assistant v4.10 catalogue (`MultiMFX.INI`): each nest's site
    height and footprint, and its Y shift. These reproduce every HHS site of the Venus-assembled
    MFX carriers shipped with Hamilton's NGS STAR protocols exactly (X, Y, Z, size).
  - The same carriers' 3D models (`MFX_CAR_*.x`), where every module appears at one translation:
    each HHS is centred in its slot and stands on the carrier's 8 mm plate; the unit is
    147.12 x 104.72 mm; its silver body ends 72.9 mm above its foot.
The split of a site's height between the unit and its nest follows the models' body/nest
colours (see `HHS_BODY_HEIGHT`); only the sum (the site height) is checked against Venus.
"""

from typing import Optional

from pylabrobot.resources.carrier import PlateHolder
from pylabrobot.resources.coordinate import Coordinate
from pylabrobot.resources.resource_holder import ResourceHolder

# The unit's footprint, from Hamilton's HHS models (HHS_FlatDWP.x and HHS_DWP_Nunc.x agree).
HHS_SIZE_X = 147.12
HHS_SIZE_Y = 104.72
# Its foot to the top of its silver body, where a nest sits: 62.9 above the model's origin, whose
# foot is 10 below it (HHS_FlatDWP.x).
HHS_BODY_HEIGHT = 72.9

# Where a nest's plate site starts inside the unit, before the nest's own Y shift: the SBS
# footprint centred in the unit, which is how the carrier's site origin (15.25 across the shaker
# carrier) and the unit's centre (78.75) relate.
_SITE_X = (HHS_SIZE_X - 127.0) / 2  # 10.06
_SITE_Y = (HHS_SIZE_Y - 86.0) / 2  # 9.36

# The riser Hamilton stands a unit on for flat MTP nests: HHS_FlatMTP.x is HHS_FlatDWP.x's unit on
# this block, and the catalogue's flat MTP site is its flat DWP site plus exactly this height.
HHS_RISER_SIZE_X = 148.0
HHS_RISER_SIZE_Y = 105.0
HHS_RISER_HEIGHT = 29.0

# The carrier's plate, where every unit's foot stands (the MFX shaker carrier; PLR's own
# `MFX_CAR_L4_SHAKER` measures the same 8.0).
_CARRIER_FLOOR = 8.0


class HamiltonHeaterShaker(ResourceHolder):
  """A Hamilton Heater Shaker: holds one nest on top, which holds the plate.

  Geometry only. The unit is controlled through `HamiltonHeaterShakerBackend`
  (`pylabrobot.legacy.heating_shaking`), over a heater-shaker box or the STAR.
  """

  def __init__(
    self,
    name: str,
    category: str = "heating_shaking",
    model: Optional[str] = "hamilton_heater_shaker",
  ):
    super().__init__(
      name=name,
      size_x=HHS_SIZE_X,
      size_y=HHS_SIZE_Y,
      size_z=HHS_BODY_HEIGHT,
      child_location=Coordinate(0, 0, HHS_BODY_HEIGHT),
      category=category,
      model=model,
    )

  @property
  def nest(self) -> Optional[PlateHolder]:
    return self.resource  # type: ignore[return-value]


def hamilton_heater_shaker(name: str, nest: Optional[PlateHolder] = None) -> HamiltonHeaterShaker:
  """A Hamilton Heater Shaker, with `nest` fitted if given."""
  hhs = HamiltonHeaterShaker(name=name)
  if nest is not None:
    hhs.assign_child_resource(nest)
  return hhs


def hamilton_heater_shaker_riser(
  name: str, heater_shaker: Optional[HamiltonHeaterShaker] = None
) -> ResourceHolder:
  """The 29 mm block a Heater Shaker stands on for flat MTP nests, with `heater_shaker` on it if
  given. From Hamilton's model of the unit with a flat MTP nest (HHS_FlatMTP.x); no part number
  in the catalogue. The unit stands centred on it."""
  riser = ResourceHolder(
    name=name,
    size_x=HHS_RISER_SIZE_X,
    size_y=HHS_RISER_SIZE_Y,
    size_z=HHS_RISER_HEIGHT,
    child_location=Coordinate(
      (HHS_RISER_SIZE_X - HHS_SIZE_X) / 2, (HHS_RISER_SIZE_Y - HHS_SIZE_Y) / 2, HHS_RISER_HEIGHT
    ),
    category="heater_shaker_riser",
    model="hamilton_heater_shaker_riser",
  )
  if heater_shaker is not None:
    riser.assign_child_resource(heater_shaker)
  return riser


def _nest(name: str, model: str, site_z: float, y_shift: float, riser: float = 0) -> PlateHolder:
  """A nest whose plate site is `site_z` above the carrier's bottom, as the catalogue gives it,
  on a unit raised by `riser`."""
  seat = site_z - _CARRIER_FLOOR - riser - HHS_BODY_HEIGHT
  return PlateHolder(
    name=name,
    size_x=HHS_SIZE_X,
    size_y=HHS_SIZE_Y,
    size_z=seat,
    child_location=Coordinate(_SITE_X, _SITE_Y + y_shift, seat),
    # Flat nests hold a plate on its skirt. For the shaped nests (Nunc, Sarstedt, PCR96 ABI) no
    # source gives a pedestal height; 0 keeps the catalogue's site height for every plate.
    pedestal_size_z=0,
    model=model,
  )


# Each nest: Hamilton part number, catalogue site height (mm above the carrier's bottom) and Y
# shift. The "mm" in the names is Hamilton's variant naming (1.5, 2 or 3 mm); what it measures is
# not stated. Checked against Venus-assembled carriers: flat MTP 3 mm, flat DWP 3 mm, Nunc DWP 3 mm.


def hamilton_hhs_nest_flat_mtp_2mm(name: str) -> PlateHolder:
  """HHS 2 mm flat MTP nest, Hamilton cat. no. 199033. Its unit stands on
  `hamilton_heater_shaker_riser`."""
  return _nest(
    name, "hamilton_hhs_nest_flat_mtp", site_z=112.7, y_shift=-1.05, riser=HHS_RISER_HEIGHT
  )


def hamilton_hhs_nest_flat_mtp_3mm(name: str) -> PlateHolder:
  """HHS 3 mm flat MTP nest, Hamilton cat. no. 199034. Its unit stands on
  `hamilton_heater_shaker_riser`."""
  return _nest(
    name, "hamilton_hhs_nest_flat_mtp", site_z=112.7, y_shift=-1.55, riser=HHS_RISER_HEIGHT
  )


def hamilton_hhs_nest_flat_dwp_2mm(name: str) -> PlateHolder:
  """HHS 2 mm flat DWP nest, Hamilton cat. no. 199033."""
  return _nest(name, "hamilton_hhs_nest_flat_dwp", site_z=83.7, y_shift=-1.05)


def hamilton_hhs_nest_flat_dwp_3mm(name: str) -> PlateHolder:
  """HHS 3 mm flat DWP nest, Hamilton cat. no. 199034."""
  return _nest(name, "hamilton_hhs_nest_flat_dwp", site_z=83.0, y_shift=-1.55)


def hamilton_hhs_nest_nunc_dwp_1_5mm(name: str) -> PlateHolder:
  """HHS 1.5 mm Nunc DWP nest, Hamilton cat. no. 199037."""
  return _nest(name, "hamilton_hhs_nest_nunc_dwp", site_z=83.25, y_shift=-0.25)


def hamilton_hhs_nest_nunc_dwp_2mm(name: str) -> PlateHolder:
  """HHS 2 mm Nunc DWP nest, Hamilton cat. no. 199038."""
  return _nest(name, "hamilton_hhs_nest_nunc_dwp", site_z=83.0, y_shift=-1.05)


def hamilton_hhs_nest_nunc_dwp_3mm(name: str) -> PlateHolder:
  """HHS 3 mm Nunc DWP nest, Hamilton cat. no. 199039."""
  return _nest(name, "hamilton_hhs_nest_nunc_dwp", site_z=83.0, y_shift=-1.55)


def hamilton_hhs_nest_sarstedt_1_5mm(name: str) -> PlateHolder:
  """HHS 1.5 mm Sarstedt nest, Hamilton cat. no. 199027. Its site is 123 x 88 mm, from the same
  origin as the SBS nests."""
  return _nest(name, "hamilton_hhs_nest_sarstedt", site_z=79.3, y_shift=-0.25)


def hamilton_hhs_nest_pcr96_abi(name: str) -> PlateHolder:
  """HHS PCR96 ABI nest, Hamilton cat. no. 188298."""
  return _nest(name, "hamilton_hhs_nest_pcr96_abi", site_z=91.2, y_shift=-1.55)
