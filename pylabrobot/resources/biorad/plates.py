import math
import warnings

from pylabrobot.resources.plate import Plate
from pylabrobot.resources.utils import create_ordered_items_2d
from pylabrobot.resources.well import (
  CrossSectionType,
  Well,
  WellBottomType,
)


def biorad_384_wellplate_50uL_Vb(name: str) -> Plate:
  return Plate(
    name=name,
    size_x=127.76,
    size_y=85.48,
    size_z=10.40,
    lid=None,
    model="biorad_384_wellplate_50uL_Vb",
    ordered_items=create_ordered_items_2d(
      Well,
      num_items_x=24,
      num_items_y=16,
      dx=10.58,
      dy=7.44,
      dz=1.05,
      item_dx=4.5,
      item_dy=4.5,
      size_x=3.10,
      size_y=3.10,
      size_z=9.35,
      bottom_type=WellBottomType.V,
      material_z_thickness=1,  # measured
      cross_section_type=CrossSectionType.CIRCLE,
      name_prefix=name,
    ),
  )


# Hard-Shell 96 low-profile well (Bio-Rad bulletin 5496): a conical frustum, 2.64 mm across at the
# bottom of the conical section and 5.46 mm at the opening. The cavity is 13.90 mm deep: the
# 14.81 mm well depth less the 0.91 mm below the cavity floor at the tip (Hamilton's model of the
# plate).
_HSP96_CAVITY_DEPTH = 13.90
_HSP96_BOTTOM_RADIUS = 2.64 / 2
_HSP96_TOP_RADIUS = 5.46 / 2


def _hsp96_radius_at(height: float) -> float:
  slope = (_HSP96_TOP_RADIUS - _HSP96_BOTTOM_RADIUS) / _HSP96_CAVITY_DEPTH
  return _HSP96_BOTTOM_RADIUS + slope * height


def _compute_volume_from_height_biorad_96_wellplate_200uL_Vb(height_mm: float) -> float:
  """Volume (uL) of liquid `height_mm` above the cavity floor of a Hard-Shell 96 well."""
  if not 0 <= height_mm <= _HSP96_CAVITY_DEPTH * 1.01:
    raise ValueError(f"Height {height_mm} is outside biorad_96_wellplate_200uL_Vb's well")
  r0, r = _HSP96_BOTTOM_RADIUS, _hsp96_radius_at(height_mm)
  return math.pi * height_mm * (r0**2 + r0 * r + r**2) / 3


def _compute_height_from_volume_biorad_96_wellplate_200uL_Vb(volume_ul: float) -> float:
  """Liquid height (mm) above the cavity floor of a Hard-Shell 96 well holding `volume_ul`."""
  max_volume = _compute_volume_from_height_biorad_96_wellplate_200uL_Vb(_HSP96_CAVITY_DEPTH)
  if not 0 <= volume_ul <= max_volume * 1.01:
    raise ValueError(f"Volume {volume_ul} is outside biorad_96_wellplate_200uL_Vb's well")
  # V(h) = pi/(3k) * (r(h)^3 - r0^3) for a cone widening by k per mm: solve for r(h).
  k = (_HSP96_TOP_RADIUS - _HSP96_BOTTOM_RADIUS) / _HSP96_CAVITY_DEPTH
  r = (_HSP96_BOTTOM_RADIUS**3 + 3 * k * volume_ul / math.pi) ** (1 / 3)
  return (r - _HSP96_BOTTOM_RADIUS) / k


def biorad_96_wellplate_200uL_Vb(name: str) -> Plate:
  """Bio-Rad Hard-Shell 96-well PCR plate, low profile, thin wall, full skirt.

  - Catalogue numbers: HSP9601 (white shell, clear wells); same geometry for the HSP-96xx colours
    and HSP-9901/9955 (bar-coded). Often called "HSP" plates.
  - Material: rigid polycarbonate shell and deck; thin-wall polypropylene wells.
  - Max. well volume 200 uL (manufacturer). The geometric cavity used here holds 186 uL to the rim.
  - Dimensions: Bio-Rad bulletin 5496 ("Microplate Dimensions, Hard-Shell Low-Profile 96-Well
    Skirted PCR Plates"): 127.76 x 85.48 x 16.06 mm, A1 14.38 mm from the left and 11.24 mm from
    the top edge, well depth 14.81 mm (rim to tip), 5.46 mm opening, 2.64 mm at the bottom of the
    conical section, 17.5 degree well angle. The rim stands 0.58 mm above the deck.
  - Cavity floor 0.91 mm above the outer well tip: from Hamilton's 3D model of the plate
    (`BioRad PCR Full Skirt White.x`, NGS STAR labware), not a manufacturer figure.

  https://www.bio-rad.com/webroot/web/pdf/lsr/literature/Bulletin_5496.pdf
  """
  return Plate(
    name=name,
    size_x=127.76,
    size_y=85.48,
    size_z=16.06,
    lid=None,
    model=biorad_96_wellplate_200uL_Vb.__name__,
    plate_type="skirted",
    ordered_items=create_ordered_items_2d(
      Well,
      num_items_x=12,
      num_items_y=8,
      dx=14.38 - 5.46 / 2,
      dy=85.48 - 11.24 - 7 * 9 - 5.46 / 2,
      dz=16.06 - 14.81,
      item_dx=9,
      item_dy=9,
      size_x=5.46,
      size_y=5.46,
      size_z=14.81,
      bottom_type=WellBottomType.V,
      material_z_thickness=14.81 - _HSP96_CAVITY_DEPTH,
      max_volume=_compute_volume_from_height_biorad_96_wellplate_200uL_Vb(_HSP96_CAVITY_DEPTH),
      cross_section_type=CrossSectionType.CIRCLE,
      compute_volume_from_height=_compute_volume_from_height_biorad_96_wellplate_200uL_Vb,
      compute_height_from_volume=_compute_height_from_volume_biorad_96_wellplate_200uL_Vb,
      name_prefix=name,
    ),
  )


# --------------------------------------------------------------------------- #
# Deprecated function names (backward compatibility)
# --------------------------------------------------------------------------- #


def BioRad_384_wellplate_50uL_Vb(name: str) -> Plate:  # remove v1b1
  """Deprecated alias for biorad_384_wellplate_50uL_Vb().

  This alias will be removed in v1b1.
  Use `biorad_384_wellplate_50uL_Vb()` instead.
  """
  warnings.warn(
    "BioRad_384_wellplate_50uL_Vb() is deprecated and will be removed in v1b1. "
    "Use biorad_384_wellplate_50uL_Vb() instead.",
    DeprecationWarning,
    stacklevel=2,
  )
  return biorad_384_wellplate_50uL_Vb(name)
