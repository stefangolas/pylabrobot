import warnings
from typing import Dict, Optional

from pylabrobot.resources.carrier import (
  Coordinate,
  MFXCarrier,
  ResourceHolder,
)
from pylabrobot.resources.hamilton.mfx_modules import (
  hamilton_mfx_odtc_lid_park,
  hamilton_mfx_plateholder_DWP_HP_tabbed,
  hamilton_mfx_plateholder_MIDI_HP_tabbed,
  hamilton_mfx_plateholder_MTP_HP_tabbed,
)


def hamilton_mfx_carrier_L5_base(name: str, modules: Dict[int, ResourceHolder]) -> MFXCarrier:
  """Hamilton cat. no.: 188039
  Hamilton name: 'MFX_CAR_L5_base'
  Labware carrier base for up to 5 Multiflex Modules
  """
  # Modules are 94 mm deep on a 96 mm pitch and centre what they hold; Hamilton's definitions place
  # that content with the modules' front edges 4.5 mm into the carrier. A caliper reads 5 to 5.5,
  # which cannot resolve half a millimetre against the carrier's chamfered edge.
  locations = [
    Coordinate(0.0, 4.5, 18.2),
    Coordinate(0.0, 100.5, 18.2),
    Coordinate(0.0, 196.5, 18.2),
    Coordinate(0.0, 292.5, 18.2),
    Coordinate(0.0, 388.5, 18.2),
  ]
  half_locations = [c + Coordinate(y=90 / 2) for c in locations[:-1]]
  sites: Dict[int, ResourceHolder] = {}
  for i, module in modules.items():
    if isinstance(i, int):
      module.location = locations[i]
    elif i - int(i) == 0.5:
      module.location = half_locations[int(i)]
    else:
      raise ValueError(f"Invalid site index: {i}")

    sites[i] = module

  return MFXCarrier(
    name=name,
    size_x=135.0,
    size_y=497.0,
    size_z=18.2,
    sites=sites,
    model="MFX_CAR_L5_base",
  )


def hamilton_mfx_carrier_L5_2MTP_MIDI_2DWP_HP_tabbed(name: str) -> MFXCarrier:
  """Hamilton's NGS STAR carrier 'MFX_CAR_2MTP HPTab_MIDI HPTab_2DWP HPTab': an L5 base with HP
  Tabbed nests, from the front: two DWP (6601988-01), a MIDI (6600518-01), two MTP (6601987-01).
  As assembled in the NGS STAR protocol labware (KAPA HyperPlus, 10x Genomics, PacBio, QIAseq).
  """
  return hamilton_mfx_carrier_L5_base(
    name,
    modules={
      0: hamilton_mfx_plateholder_DWP_HP_tabbed(f"{name}_dwp_0"),
      1: hamilton_mfx_plateholder_DWP_HP_tabbed(f"{name}_dwp_1"),
      2: hamilton_mfx_plateholder_MIDI_HP_tabbed(f"{name}_midi"),
      3: hamilton_mfx_plateholder_MTP_HP_tabbed(f"{name}_mtp_0"),
      4: hamilton_mfx_plateholder_MTP_HP_tabbed(f"{name}_mtp_1"),
    },
  )


def hamilton_mfx_carrier_7T_odtc(
  name: str, odtc: Optional[ResourceHolder] = None, lid_park: bool = True
) -> MFXCarrier:
  """Hamilton's NGS STAR carrier 'MFX_CAR_ODTC_MTP' ("7T Carrier with ODTC and Park Position for
  Hamilton Comfort Lid"): the MFX shaker carrier with an Inheco ODTC on its plate and, in front, a
  park for the ODTC's ComfortLid.

  `odtc` is the ODTC resource (e.g. `pylabrobot.legacy.thermocycling.inheco.inheco_odtc`); it is
  placed so that a plate in it stands where Hamilton's template puts it (site 1_ODTC: X 15.25, Y
  158.8, 94.5 above the carrier's bottom, 127 x 86). The lid park's lid site is 3_MFX (X 15.25,
  Y 14.1, 107).
  """
  return _odtc_carrier(name, odtc, lid_park, odtc_site_z=94.5)


def hamilton_mfx_carrier_7T_odtc_v2(
  name: str, odtc: Optional[ResourceHolder] = None, lid_park: bool = True
) -> MFXCarrier:
  """Hamilton's revised template for the same carrier, 'MFX_CAR_ODTC_MTP_V2' (NGS STAR KAPA
  HyperPlus, PacBio and Avenio kits): the ODTC's plate site 2.6 higher, at 97.1 above the
  carrier's bottom (its lid site at 109.1); everything else as `hamilton_mfx_carrier_7T_odtc`.

  The two templates share one 3D model, and the Bio-Rad plate definition shipped with V2 changes
  only its well opening (5.40 -> 5.46), so the 2.6 is a change to the site, not to the plate. The
  ODTC is raised to match and stands 2.6 above the carrier's plate: Hamilton's data does not say
  what physically raises it.

  V2 is also anchored differently: one track wide, at the carrier's right, with every site 201.8
  to the left and 12.5 in front of V1's. That is where the kits mount the carrier (left of track 1,
  see the NGS decks), not a property of the carrier, so it is not modelled here.
  """
  return _odtc_carrier(name, odtc, lid_park, odtc_site_z=97.1)


def _odtc_carrier(
  name: str, odtc: Optional[ResourceHolder], lid_park: bool, odtc_site_z: float
) -> MFXCarrier:
  sites: Dict[int, ResourceHolder] = {}
  if lid_park:
    park = hamilton_mfx_odtc_lid_park(f"{name}_lid_park")
    # centred on the template's lid site
    park.location = Coordinate(
      15.25 + 127.0 / 2 - park.get_size_x() / 2, 14.1 + 86.0 / 2 - park.get_size_y() / 2, 8.0
    )
    sites[0] = park
  if odtc is not None:
    # the template's 127 x 86 plate site, an SBS plate centred on it
    plate = Coordinate(15.25 + (127.0 - 127.76) / 2, 158.8 + (86.0 - 85.48) / 2, odtc_site_z)
    odtc.location = plate - odtc.child_location
    sites[1] = odtc
  return MFXCarrier(
    name=name,
    size_x=157.5,
    size_y=497.0,
    size_z=8.0,
    sites=sites,
    model="MFX_CAR_7T_shaker",
  )


def MFX_CAR_L4_SHAKER(name: str, modules: Dict[int, ResourceHolder]) -> MFXCarrier:
  """Hamilton cat. no.: 187001
  Sometimes referred to as "PLT_CAR_L4_SHAKER" by Hamilton.
  Template carrier with 4 positions for Hamilton Heater Shaker in landscape.
  Occupies 7 tracks (7T). Can be screwed onto the deck.

  The same carrier as `hamilton_mfx_carrier_7T_shaker`, whose positions (from Hamilton's data)
  it now uses. Its earlier positions were measured in the lab at two slots (365.0 with an HHS,
  0.7 mm from Hamilton's) and interpolated at a 121 mm pitch at the other two.
  """
  return hamilton_mfx_carrier_7T_shaker(name, modules)


def hamilton_mfx_carrier_7T_shaker(name: str, modules: Dict[int, ResourceHolder]) -> MFXCarrier:
  """Hamilton MFX 4 position carrier for Heater Shakers ('MFX_CAR_7T', the Multiflex Carrier
  Assistant's shaker carrier). 7 tracks wide; index 0 is the front position (Hamilton's position 4).

  Each position holds a Hamilton Heater Shaker (`hamilton_heater_shaker`), or one on its riser
  (`hamilton_heater_shaker_riser`), centred in its slot on the carrier's 8 mm plate, 120 mm
  apart. From Hamilton's data: the catalogue gives the pitch (-120 mm from position 1 at the back)
  and the site origin (15.25, 375.05); the carrier's 3D model and the Venus-assembled carriers
  place each unit's centre at X 78.75, Y 58.05 + 120 i, on the plate at Z 8. Also available as
  `MFX_CAR_L4_SHAKER`.
  """
  sites: Dict[int, ResourceHolder] = {}
  for i, module in modules.items():
    # centred on the slot's centre, whatever the module's footprint
    module.location = Coordinate(
      78.75 - module.get_size_x() / 2, 58.05 + 120.0 * i - module.get_size_y() / 2, 8.0
    )
    sites[i] = module

  return MFXCarrier(
    name=name,
    size_x=157.5,
    size_y=497.0,
    size_z=8.0,  # the plate the units stand on; its side rails reach 21.5
    sites=sites,
    model="MFX_CAR_7T_shaker",
  )


def MFX_CAR_P3_SHAKER(name: str, modules: Dict[int, ResourceHolder]) -> MFXCarrier:
  """Hamilton cat. no.: 187001
  Sometimes referred to as "PLT_CAR_L4_SHAKER" by Hamilton, this one has extra holes for portrait orientation shakers.
    (you can drill these yourself, if you're adventurous)
  Some but not all of these carriers have:
    - extra holes for 3 portrait positions
    - extra holes for mounting a thermocycler
  This is a template carrier for setups with 3 positions for Hamilton Heater Shakers in portrait.
  Occupies 7 tracks (7T). Can be screwed onto the deck.
  Tested with hamilton heated shaker: HeaterShaker(size_x=146.2, size_y=103.6, size_z=74.11, child_location=Coordinate(x=10, y=13, z=74.24))
  """
  locations = [
    Coordinate(26.45, 0, 8.0),
    Coordinate(26.45, 146.2 + 17.2, 8.0),
    Coordinate(26.45, (146.2) * 2 + 17.2 + 11.6, 8.0),
  ]
  sites: Dict[int, ResourceHolder] = {}
  for i, module in modules.items():
    module.location = locations[i]
    sites[i] = module

  return MFXCarrier(
    name=name,
    size_x=157.5,
    size_y=497.0,
    size_z=8.0,
    sites=sites,
    model="MFX_CAR_P3_SHAKER",
  )


def MFX_CAR_P3_base(name: str, modules: Dict[int, ResourceHolder]) -> MFXCarrier:
  """Hamilton cat. no.: 188053
  Labware carrier base for up to 3 Multiflex Modules in Portrait orientation
  Does not support half-indices
  Occupies 5 tracks (5T)
  """
  locations = [
    Coordinate(16.6, 35.2, 18.195),
    Coordinate(16.6, 179.2, 18.195),
    Coordinate(16.6, 325.2, 18.195),
  ]
  sites: Dict[int, ResourceHolder] = {}
  for i, module in modules.items():
    module.location = locations[i]
    sites[i] = module

  return MFXCarrier(
    name=name,
    size_x=112.5,
    size_y=497.0,
    size_z=18.195,
    sites=sites,
    model="MFX_CAR_P3_base",
  )


# Deprecated names for backwards compatibility
# TODO: Remove >2026-02


def MFX_CAR_L5_base(name: str, modules: Dict[int, ResourceHolder]) -> MFXCarrier:
  """Deprecated alias for `hamilton_mfx_carrier_L5_base`."""
  warnings.warn(
    "MFX_CAR_L5_base is deprecated. Use 'hamilton_mfx_carrier_L5_base' instead.",
    DeprecationWarning,
    stacklevel=2,
  )
  return hamilton_mfx_carrier_L5_base(name, modules)
