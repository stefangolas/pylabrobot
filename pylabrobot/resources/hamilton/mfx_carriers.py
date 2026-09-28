import warnings
from typing import Dict

from pylabrobot.resources.carrier import (
  Coordinate,
  MFXCarrier,
  ResourceHolder,
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


def MFX_CAR_L4_SHAKER(name: str, modules: Dict[int, ResourceHolder]) -> MFXCarrier:
  """Hamilton cat. no.: 187001
  Sometimes referred to as "PLT_CAR_L4_SHAKER" by Hamilton.
  Template carrier with 4 positions for Hamilton Heater Shaker in landscape.
  Occupies 7 tracks (7T). Can be screwed onto the deck.
  """
  locations = [
    Coordinate(6.0, 2, 8.0),  # not tested, interpolated Coordinate
    Coordinate(6.0, 123, 8.0),  # not tested, interpolated Coordinate
    Coordinate(6.0, 244.0, 8.0),  # tested using Hamilton_HC
    Coordinate(6.0, 365.0, 8.0),  # tested using Hamilton_HS
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
    model="PLT_CAR_L4_SHAKER",
  )


def hamilton_mfx_carrier_7T_shaker(name: str, modules: Dict[int, ResourceHolder]) -> MFXCarrier:
  """Hamilton MFX 4 position carrier for Heater Shakers ('MFX_CAR_7T', the Multiflex Carrier
  Assistant's shaker carrier). 7 tracks wide; index 0 is the front position (Hamilton's position 4).

  Each position holds a Hamilton Heater Shaker (`hamilton_heater_shaker`), or one on its riser
  (`hamilton_heater_shaker_riser`), centred in its slot on the carrier's 8 mm plate, 120 mm
  apart. From Hamilton's data: the catalogue gives the pitch (-120 mm from position 1 at the back)
  and the site origin (15.25, 375.05); the carrier's 3D model and the Venus-assembled carriers
  place each unit's centre at X 78.75, Y 58.05 + 120 i, on the plate at Z 8. `MFX_CAR_L4_SHAKER` is the same carrier with positions measured in the lab
  (365.0 tested with an HHS, 0.7 mm from this) and two interpolated at a 121 mm pitch.
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
