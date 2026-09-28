"""Bio-Rad Hard-Shell 96 plate against Bio-Rad's drawing, and its model against the plate."""

import json
import struct
import unittest
from pathlib import Path

from pylabrobot.resources import Plate, Resource, biorad_96_wellplate_200uL_Vb

MODEL_DIR = Path(__file__).parent / "resource_model"


def glb_bounds_mm(path: Path):
  """Min and max corner (mm) over every POSITION accessor in a GLB, from its JSON chunk."""
  data = path.read_bytes()
  (length,) = struct.unpack("<I", data[12:16])
  gltf = json.loads(data[20 : 20 + length])
  accessors = [
    gltf["accessors"][p["attributes"]["POSITION"]]
    for mesh in gltf["meshes"]
    for p in mesh["primitives"]
  ]
  lo = [min(a["min"][i] for a in accessors) * 1000 for i in range(3)]
  hi = [max(a["max"][i] for a in accessors) * 1000 for i in range(3)]
  return lo, hi


def well_centre(plate: Plate, identifier: str):
  well = plate.get_well(identifier)
  assert well.location is not None
  return (well.location.x + well.get_size_x() / 2, well.location.y + well.get_size_y() / 2)


class BioRadHardShell96Tests(unittest.TestCase):
  def setUp(self) -> None:
    self.plate = biorad_96_wellplate_200uL_Vb("hsp")

  def test_well_offsets_match_bulletin_5496(self) -> None:
    """A1 14.38 from the left and 11.24 from the top; H12 113.38 and 74.24."""
    x, y = well_centre(self.plate, "A1")
    self.assertAlmostEqual(x, 14.38)
    self.assertAlmostEqual(85.48 - y, 11.24)
    x, y = well_centre(self.plate, "H12")
    self.assertAlmostEqual(x, 113.38)
    self.assertAlmostEqual(85.48 - y, 74.24)

  def test_wells_run_from_tip_to_rim(self) -> None:
    well = self.plate.get_well("A1")
    assert well.location is not None
    self.assertAlmostEqual(well.location.z + well.get_size_z(), 16.06)
    self.assertAlmostEqual(well.get_size_z(), 14.81)

  def test_volume_and_height_are_inverse(self) -> None:
    well = self.plate.get_well("A1")
    self.assertAlmostEqual(well.max_volume, 186.3, places=1)
    for volume in [0.5, 10, 50, 150, 186]:
      with self.subTest(volume=volume):
        height = well.compute_height_from_volume(volume)
        self.assertAlmostEqual(well.compute_volume_from_height(height), volume, places=6)

  def test_geometry_survives_serialization(self) -> None:
    """Volume functions are not carried through serialization; positions and sizes are."""
    copy = Resource.deserialize(self.plate.serialize())
    assert isinstance(copy, Plate)
    for identifier in ["A1", "H12"]:
      self.assertEqual(copy.get_well(identifier).location, self.plate.get_well(identifier).location)
    self.assertEqual(copy.get_well("A1").max_volume, self.plate.get_well("A1").max_volume)

  def test_model_is_registered_to_the_plate(self) -> None:
    """The model's wells are on the plate's wells, so its outline sits at most 0.35 mm off."""
    lo, hi = glb_bounds_mm(MODEL_DIR / f"{self.plate.model}.glb")
    for got, want in zip(lo, [0, 0, 0]):
      self.assertAlmostEqual(got, want, delta=0.36)
    for got, want in zip(hi, [127.76, 85.48, 16.06]):
      self.assertAlmostEqual(got, want, delta=0.36)


if __name__ == "__main__":
  unittest.main()
