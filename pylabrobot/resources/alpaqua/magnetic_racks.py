import warnings

# implemented as PlateAdapter to enable simple and fast assignment
# of plates to them, with self-correcting location placement
from pylabrobot.resources.plate_adapter import PlateAdapter


def alpaqua_96_plateadapter_magnum_flx(name: str) -> PlateAdapter:
  """Alpaqua Engineering LLC cat. no.: A000400
  Magnetic rack for 96-well plates.
  implemented as PlateAdapter to enable simple and fast assignment of
    plates to them, with self-correcting location placement
  """
  return PlateAdapter(
    name=name,
    size_x=127.76,
    size_y=85.48,
    size_z=35.0,
    dx=9.8,
    dy=6.8,
    dz=27.5,  # refers to magnet hole bottom
    plate_z_offset=0.0,  # adjust at runtime based on plate's well geometry
    adapter_hole_size_x=8.0,
    adapter_hole_size_y=8.0,
    adapter_hole_size_z=8.0,  # guesstimate
    model=alpaqua_96_plateadapter_magnum_flx.__name__,
  )


def alpaqua_96_plateadapter_magnum_ex(name: str) -> PlateAdapter:
  """Alpaqua Engineering LLC cat. no.: A000380
  Magnum EX universal magnet plate: 96 ring magnets on an elevated platform.

  From Alpaqua's drawing A000380-WS Rev. A: base 127.76 x 85.60, 35.14 high, 12 x 8 ring magnets
  9.00 across at a 9.00 pitch, centred on the base, their tops at 28.79 (35.14 - 6.35).

  The plate seat, 29.21 above the base, is Hamilton's: their Magnum EX template
  (`Alpaqua_MagEx.tml`) seats plates there, and every Hamilton NGS STAR kit that uses this magnet
  pipettes an Abgene MIDI plate on it. A plate that sits in the rings rather than on them (a PCR
  plate) would need its own `plate_z_offset`.
  """
  return PlateAdapter(
    name=name,
    size_x=127.76,
    size_y=85.60,
    size_z=35.14,
    dx=(127.76 - 108.0) / 2,  # the H1 ring's left edge
    dy=(85.60 - 72.0) / 2,  # the H1 ring's front edge
    dz=29.21,
    adapter_hole_size_x=9.0,
    adapter_hole_size_y=9.0,
    model=alpaqua_96_plateadapter_magnum_ex.__name__,
  )


# Deprecated names for backwards compatibility
# TODO: Remove >2026-02


def Alpaqua_96_magnum_flx(name: str) -> PlateAdapter:
  """Deprecated alias for `alpaqua_96_plateadapter_magnum_flx`."""
  warnings.warn(
    "Alpaqua_96_magnum_flx is deprecated. Use 'alpaqua_96_plateadapter_magnum_flx' instead.",
    DeprecationWarning,
    stacklevel=2,
  )
  return alpaqua_96_plateadapter_magnum_flx(name)
