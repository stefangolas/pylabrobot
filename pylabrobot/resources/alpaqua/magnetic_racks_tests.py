"""The Alpaqua Magnum EX against Alpaqua's drawing and Hamilton's NGS STAR placement of it."""

import json
import struct
import unittest
from pathlib import Path

from pylabrobot.resources.alpaqua import alpaqua_96_plateadapter_magnum_ex
from pylabrobot.resources.biorad.plates_tests import glb_bounds_mm, well_centre
from pylabrobot.resources.hamilton.mfx_carriers import (
  hamilton_mfx_carrier_L5_2MTP_MIDI_2DWP_HP_tabbed,
)
from pylabrobot.resources.thermo_fisher import thermo_TS_abgene_96_wellplate_800uL_Vb

MODEL = Path(__file__).parent / "resource_model" / "alpaqua_96_plateadapter_magnum_ex.glb"


def glb_mesh_bounds_mm(path: Path, name: str):
  """Min and max corner (mm) of one named mesh in a GLB."""
  data = path.read_bytes()
  (length,) = struct.unpack("<I", data[12:16])
  gltf = json.loads(data[20 : 20 + length])
  (mesh,) = [m for m in gltf["meshes"] if m.get("name") == name]
  accessors = [gltf["accessors"][p["attributes"]["POSITION"]] for p in mesh["primitives"]]
  lo = [min(a["min"][i] for a in accessors) * 1000 for i in range(3)]
  hi = [max(a["max"][i] for a in accessors) * 1000 for i in range(3)]
  return lo, hi


class MagnumEXTests(unittest.TestCase):
  # Alpaqua drawing A000380-WS Rev. A.
  BASE = (127.76, 85.60, 35.14)
  RING_TOPS = 35.14 - 6.35
  # Rings 12 x 8 at 9.00, spanning 108.00, centred on the base: the ring centres of A1 and H1.
  A1 = ((127.76 - 108.0) / 2 + 4.5, (85.60 + 72.0) / 2 - 4.5)
  H1 = ((127.76 - 108.0) / 2 + 4.5, (85.60 - 72.0) / 2 + 4.5)
  # Hamilton's Magnum EX template `Alpaqua_MagEx.tml`: site "Magnet" at Z 29.21.
  SEAT = 29.21

  def test_size_is_alpaquas(self):
    magnet = alpaqua_96_plateadapter_magnum_ex("magnet")
    size = (magnet.get_size_x(), magnet.get_size_y(), magnet.get_size_z())
    for got, want in zip(size, self.BASE):
      self.assertAlmostEqual(got, want, places=6)

  def test_the_midi_plates_wells_are_over_the_rings(self):
    magnet = alpaqua_96_plateadapter_magnum_ex("magnet")
    plate = thermo_TS_abgene_96_wellplate_800uL_Vb("midi")
    magnet.assign_child_resource(plate)
    for identifier, (x, y) in (("A1", self.A1), ("H1", self.H1)):
      with self.subTest(well=identifier):
        wx, wy = well_centre(plate, identifier)
        self.assertAlmostEqual(plate.location.x + wx, x, places=6)
        self.assertAlmostEqual(plate.location.y + wy, y, places=6)
    self.assertAlmostEqual(plate.location.z, self.SEAT, places=6)
    self.assertGreater(plate.location.z, self.RING_TOPS)  # resting on the rings, not in them

  def test_on_the_hp_tabbed_carriers_front_nest(self):
    """Hamilton's NGS STAR decks stand the magnet in the front DWP nest (site Z 82.4) of
    `MFX_CAR_2MTP HPTab_MIDI HPTab_2DWP HPTab`: the MIDI plate sits at 82.4 + 29.21."""
    carrier = hamilton_mfx_carrier_L5_2MTP_MIDI_2DWP_HP_tabbed("car")
    magnet = alpaqua_96_plateadapter_magnum_ex("magnet")
    carrier.sites[0].assign_child_resource(magnet)
    plate = thermo_TS_abgene_96_wellplate_800uL_Vb("midi")
    magnet.assign_child_resource(plate)
    self.assertAlmostEqual(magnet.get_location_wrt(carrier).z, 82.4, places=6)
    self.assertAlmostEqual(plate.get_location_wrt(carrier).z, 82.4 + self.SEAT, places=6)

  def test_one_plate_moves_between_nest_and_magnet(self):
    """Venus names the plate on the magnet and off it as two labware; here it is one plate, and its
    liquid goes with it."""
    carrier = hamilton_mfx_carrier_L5_2MTP_MIDI_2DWP_HP_tabbed("car")
    magnet = alpaqua_96_plateadapter_magnum_ex("magnet")
    carrier.sites[0].assign_child_resource(magnet)
    plate = thermo_TS_abgene_96_wellplate_800uL_Vb("midi")
    carrier.sites[2].assign_child_resource(plate)
    plate.get_well("A1").set_volume(150.0)
    plate.unassign()
    magnet.assign_child_resource(plate)
    self.assertIs(plate.parent, magnet)
    self.assertAlmostEqual(plate.get_well("A1").tracker.get_used_volume(), 150.0)

  def test_the_model_is_in_the_resource_frame(self):
    lo, hi = glb_bounds_mm(MODEL)
    self.assertAlmostEqual(lo[2], 0.0, delta=0.01)
    self.assertAlmostEqual((lo[0] + hi[0]) / 2, self.BASE[0] / 2, delta=0.01)
    base_lo, base_hi = glb_mesh_bounds_mm(MODEL, "alpaqua_blue_anodized")
    for axis in (0, 1):
      self.assertAlmostEqual(base_lo[axis], 0.0, delta=0.01)
      self.assertAlmostEqual(base_hi[axis], self.BASE[axis], delta=0.01)
    rings_lo, rings_hi = glb_mesh_bounds_mm(MODEL, "nickel_plated")
    self.assertAlmostEqual(rings_hi[2], self.RING_TOPS, delta=0.02)
    self.assertAlmostEqual(rings_lo[0] + 4.5, self.A1[0], delta=0.02)
    self.assertAlmostEqual(rings_hi[1] - 4.5, self.A1[1], delta=0.02)


if __name__ == "__main__":
  unittest.main()
