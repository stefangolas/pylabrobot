import warnings
from typing import Optional

from pylabrobot.resources.carrier import Coordinate, PlateHolder
from pylabrobot.resources.resource_holder import ResourceHolder
from pylabrobot.resources.tip_rack_holder import EmbeddedTipRackHolder
from pylabrobot.resources.tube_rack import TubeRack
from pylabrobot.resources.utils import create_ordered_items_2d


def hamilton_mfx_tiprackholder_standard(name: str) -> EmbeddedTipRackHolder:
  """Hamilton cat. no.: 188160
  Hamilton name: 'MFX_TIP_module' or sometimes 'Tip Module BC'
  Module to position a high-, standard- or low volume tip rack (but not a 384 tip rack).

  Takes an `EmbeddedTipRack` - Hamilton calls these 'framed' tip racks - which sinks into the
  module's opening and is centred over it, as in a tip carrier's site.
  """

  top = 114.7 - 18.2  # above the carrier's own height

  return EmbeddedTipRackHolder(
    name=name,
    size_x=135.0,
    size_y=94.0,
    size_z=top,
    # Only the height: the holder centres a framed rack in X and Y and sinks it into its opening.
    child_location=Coordinate(x=0.0, y=0.0, z=top),
    model=hamilton_mfx_tiprackholder_standard.__name__,
  )


def MFX_TIP_module(name: str) -> EmbeddedTipRackHolder:
  """Deprecated: use `hamilton_mfx_tiprackholder_standard`."""
  warnings.warn(
    "MFX_TIP_module is deprecated and will be removed in the future. "
    "Use 'hamilton_mfx_tiprackholder_standard' instead.",
    DeprecationWarning,
    stacklevel=2,
  )
  return hamilton_mfx_tiprackholder_standard(name=name)


def hamilton_mfx_resourceholder_ntr(name: str) -> ResourceHolder:
  """Hamilton cat. no.: 191425
  Hamilton name: '_NTR4' site of an MFX carrier.
  Module to position a stack of up to 4x 96 nested tip racks (NTR).
  """

  return ResourceHolder(
    name=name,
    # 134 mm across, as every MFX module is, and modelled as the 135 mm its carrier slot is: the
    # track's sliding blocks centre the module in it.
    size_x=135.0,
    size_y=94.0,  # Hamilton's NTR4Module 3D model
    size_z=20.0,  # measured
    # The rack stands centred in the module's pocket, its SBS footprint on the module's centre.
    child_location=Coordinate(x=(135.0 - 127.76) / 2, y=(94.0 - 85.48) / 2, z=10.8),
    model=hamilton_mfx_resourceholder_ntr.__name__,
  )


# -- HP Tabbed plate nests ----------------------------------------------------------------------
# Hamilton's height-adjusted nests with corner tabs, which bring an MTP, a MIDI plate and a DWP to
# about the same top height. From Hamilton's Multiflex catalogue (MultiMFX.INI, "HP Tabbed"): the
# plate site is 127 x 86 at X 4 and Y 8.5 + 96 i on the L5 base, at the catalogue's height above
# the carrier's bottom; Hamilton's NGS STAR carrier `MFX_CAR_2MTP HPTab_MIDI HPTab_2DWP HPTab`
# has exactly these sites. On PLR's L5 base the module stands at (0, 4.5 + 96 i, 18.2).
_L5_MODULE_Z = 18.2


def _hp_tabbed(name: str, model: str, site_z: float) -> PlateHolder:
  seat = site_z - _L5_MODULE_Z
  return PlateHolder(
    name=name,
    size_x=135.0,
    size_y=94.0,
    size_z=seat,
    child_location=Coordinate(4.0, 4.0, seat),
    model=model,
    pedestal_size_z=0,
  )


def hamilton_mfx_plateholder_MTP_HP_tabbed(name: str) -> PlateHolder:
  """Hamilton cat. no.: 6601987-01, MTP HP Tabbed. Plate site 109.7 above the carrier's bottom."""
  return _hp_tabbed(name, hamilton_mfx_plateholder_MTP_HP_tabbed.__name__, site_z=109.7)


def hamilton_mfx_plateholder_DWP_HP_tabbed(name: str) -> PlateHolder:
  """Hamilton cat. no.: 6601988-01, DWP HP Tabbed. Plate site 82.4 above the carrier's bottom."""
  return _hp_tabbed(name, hamilton_mfx_plateholder_DWP_HP_tabbed.__name__, site_z=82.4)


def hamilton_mfx_plateholder_MIDI_HP_tabbed(name: str) -> PlateHolder:
  """Hamilton cat. no.: 6600518-01, MIDI HP Tabbed, for the Abgene 0.8 mL MIDI plate. Plate site
  94.8 above the carrier's bottom."""
  return _hp_tabbed(name, hamilton_mfx_plateholder_MIDI_HP_tabbed.__name__, site_z=94.8)


def hamilton_mfx_plateholder_DWP_HP_tabbed_old(name: str) -> PlateHolder:
  """Hamilton cat. no.: 98553-01, the older DWP HP Tabbed nest, on its bracket (188133) for the MFX
  shaker carrier (`hamilton_mfx_carrier_7T_shaker`).

  From Hamilton's Multiflex catalogue ("DWP HPTab OLD"): plate site 127 x 86 at 84 above the
  carrier's bottom. The 134 x 100 x 10 bracket (BracketShakerBase.x) stands on the carrier's 8 mm
  plate like the CPAC's, with the nest on it and the site centred, so the site is 66 above the
  nest's foot.
  """
  seat = 84.0 - 8.0  # the site above the carrier's bottom, less the carrier's plate
  return PlateHolder(
    name=name,
    size_x=134.0,
    size_y=100.0,
    size_z=seat,
    child_location=Coordinate((134.0 - 127.0) / 2, (100.0 - 86.0) / 2, seat),
    model=hamilton_mfx_plateholder_DWP_HP_tabbed_old.__name__,
    pedestal_size_z=0,
  )


def hamilton_mfx_cpac_bracket(name: str, cpac: Optional[ResourceHolder] = None) -> ResourceHolder:
  """Hamilton's bracket for an Inheco CPAC Ultraflat on the MFX shaker carrier (the Multiflex
  catalogue's "CPAC Flat" module: "modified base", brackets 188362), with `cpac` on it if given
  (`pylabrobot.inheco.inheco_cpac_ultraflat`).

  134 x 100 x 10, from Hamilton's model (BracketShakerBaseCPAC.x); the CPAC stands centred on it,
  as Hamilton's assembled carriers draw it.
  """
  bracket = ResourceHolder(
    name=name,
    size_x=134.0,
    size_y=100.0,
    size_z=10.0,
    # centres the CPAC Ultraflat's 129 x 89 footprint
    child_location=Coordinate(x=(134.0 - 129.0) / 2, y=(100.0 - 89.0) / 2, z=10.0),
    category="cpac_bracket",
    model=hamilton_mfx_cpac_bracket.__name__,
  )
  if cpac is not None:
    bracket.assign_child_resource(cpac)
  return bracket


def hamilton_cpac_tube_block_2mL(name: str) -> TubeRack:
  """Hamilton's 24-position 2 mL tube block for the Inheco CPAC (the Multiflex catalogue's
  "CPAC 2mL" module). Stands on the CPAC as its thermal adapter:
  `inheco_cpac_ultraflat(..., adapter="tubes_2mL")`.

  From Hamilton's rack definition (CPAC_2mLTubes.rck, for eppendorf_2ml.ctr): 4 x 6 positions at
  18 mm, A1 18 mm from the left and 16.5 mm from the back of its 127 x 86 footprint, 40 tall, a
  tube's floor 0.6 above the block's bottom. Here on the SBS 127.76 x 85.48 footprint, the grid kept
  on the same centre. Hamilton's 3D model of the block (CPACTubeModule.x) draws the holes within
  0.5 mm of these. A tube stands on the block's bottom; each position is sized to an Eppendorf 2 mL
  tube (10.33 across) so that one stands centred on it.
  """
  tube = 10.33
  a1_x = 18.0 + (127.76 - 127.0) / 2
  a1_y = (86.0 - 16.5) - (86.0 - 85.48) / 2
  return TubeRack(
    name=name,
    size_x=127.76,
    size_y=85.48,
    size_z=40.0,
    model=hamilton_cpac_tube_block_2mL.__name__,
    ordered_items=create_ordered_items_2d(
      ResourceHolder,
      num_items_x=6,
      num_items_y=4,
      dx=a1_x - tube / 2,
      dy=a1_y - 3 * 18.0 - tube / 2,
      dz=0.0,
      item_dx=18.0,
      item_dy=18.0,
      size_x=tube,
      size_y=tube,
      size_z=40.0,
      name_prefix=name,
    ),
  )


def hamilton_mfx_odtc_lid_park(name: str) -> ResourceHolder:
  """The ComfortLid park of Hamilton's ODTC carrier ('MFX_CAR_ODTC_MTP', site 3_MFX), holding a
  `hamilton_pcr_comfort_lid` while the plate is out of the ODTC.

  Hamilton models it only inside the carrier's assembly; its model here is cut out of that:
  134.3 x 100, 104 tall. A lid stands centred on it, its bottom 99 above the module's foot (the
  carrier template's lid site, 107 above the carrier's bottom, less the carrier's 8 mm plate).
  """
  return ResourceHolder(
    name=name,
    size_x=134.3,
    size_y=100.0,
    size_z=104.0,
    child_location=Coordinate((134.3 - 127.5) / 2, (100.0 - 85.3) / 2, 107.0 - 8.0),
    category="lid_park",
    model=hamilton_mfx_odtc_lid_park.__name__,
  )


# -- Plate storage ---------------------------------------------------------------------------


def hamilton_mfx_plateholder_DWP_flat(name: str) -> PlateHolder:
  """Hamilton cat. no.: 188229
  Hamilton name: 'MFX_DWP_rackbased_module'
  Module to position a Deep Well Plate / tube racks (MATRIX or MICRONICS) / NUNC reagent trough.
  """

  # resource_size_x=127.76,
  # resource_size_y=85.48,

  return PlateHolder(
    name=name,
    size_x=135.0,
    size_y=94.0,
    size_z=178.0 - 18.2 - 100,  # 59.8 mm
    # probe height - carrier_height - deck_height
    child_location=Coordinate(4.0, 3.5, 178.0 - 18.2 - 100),
    model=hamilton_mfx_plateholder_DWP_flat.__name__,
    pedestal_size_z=0,
  )


def hamilton_mfx_plateholder_DWP_metal_tapped(name: str) -> PlateHolder:
  """Hamilton MFX DWP Module (cat.-no. 188042 / 188042-00).
  Hamilton name: 'MFX_DWP_rackbased_module'
  It also contains metal clamps at the corners.
  https://www.hamiltoncompany.com/other-robotics/188042
  """

  return PlateHolder(
    name=name,
    size_x=135.0,  # measured
    size_y=94.0,  # measured
    size_z=76.4,  # measured
    # probe height - carrier_height - deck_height
    child_location=Coordinate(4.0, 4.0, 183.95 - 18.2 - 100),  # measured
    pedestal_size_z=-4.74,
    model=hamilton_mfx_plateholder_DWP_metal_tapped.__name__,
  )


def MFX_DWP_module_flat(name: str) -> PlateHolder:
  """Hamilton cat. no.: 6601988-01
  Hamilton name: 'MFX_DWP_module_flat'
  Module to position a Deep Well Plate. Flat, metal base; no metal clamps.
  Grey plastic corner clips secure plate. Plates rest on corners,
  rather than pedestal, so pedestal_size_z=0,
  """

  # 134 mm measured, and modelled as the 135 mm its carrier slot is: the track's sliding blocks centre
  # the module in it, so a plate centred on the module is centred on the slot.
  width = 135.0
  length = 92.10

  return PlateHolder(
    name=name,
    size_x=width,
    size_y=length,
    size_z=66.4,  # measured with caliper
    child_location=Coordinate(x=(width - 127.76) / 2, y=(length - 85.48) / 2, z=66.4),
    model=MFX_DWP_module_flat.__name__,
    pedestal_size_z=0,
  )


# --------------------------------------------------------------------------------------------
# Deprecated names for backwards compatibility
# TODO: Remove >2026-12


def Hamilton_MFX_plateholder_DWP_metal_tapped(name: str) -> PlateHolder:
  """Deprecated alias for `hamilton_mfx_plateholder_DWP_metal_tapped`."""
  warnings.warn(
    "Hamilton_MFX_plateholder_DWP_metal_tapped is deprecated. Use 'hamilton_mfx_plateholder_DWP_metal_tapped' instead.",
    DeprecationWarning,
    stacklevel=2,
  )
  return hamilton_mfx_plateholder_DWP_metal_tapped(name)


def MFX_DWP_rackbased_module(name: str) -> PlateHolder:
  """Deprecated alias for `hamilton_mfx_plateholder_DWP_flat`."""
  warnings.warn(
    "MFX_DWP_rackbased_module is deprecated. Use 'hamilton_mfx_plateholder_DWP_flat' instead.",
    DeprecationWarning,
    stacklevel=2,
  )
  return hamilton_mfx_plateholder_DWP_flat(name)
