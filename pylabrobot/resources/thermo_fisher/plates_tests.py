"""Abgene 0.8 mL MIDI plate against Hamilton's model of it."""

import unittest
from pathlib import Path

from pylabrobot.resources import Plate, Resource, thermo_TS_abgene_96_wellplate_800uL_Vb
from pylabrobot.resources.biorad.plates_tests import glb_bounds_mm, well_centre

MODEL_DIR = Path(__file__).parent / "resource_model"


class AbgeneMidiTests(unittest.TestCase):
  def setUp(self) -> None:
    self.plate = thermo_TS_abgene_96_wellplate_800uL_Vb("midi")

  def test_wells_on_the_ansi_grid(self) -> None:
    x, y = well_centre(self.plate, "A1")
    self.assertAlmostEqual(x, 14.38)
    self.assertAlmostEqual(85.48 - y, 11.24)
    x, y = well_centre(self.plate, "H12")
    self.assertAlmostEqual(x, 14.38 + 99)
    self.assertAlmostEqual(85.48 - y, 11.24 + 63)

  def test_wells_reach_the_top_of_the_plate(self) -> None:
    well = self.plate.get_well("A1")
    assert well.location is not None
    self.assertAlmostEqual(well.location.z + well.get_size_z(), self.plate.get_size_z())

  def test_volume_and_height_are_inverse(self) -> None:
    well = self.plate.get_well("A1")
    self.assertAlmostEqual(well.max_volume, 1032, delta=1)
    self.assertGreater(well.max_volume, 800)
    for volume in [0.5, 20, 63.9, 64.5, 300, 800, 1030]:
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

  def test_model_fits_the_plate(self) -> None:
    lo, hi = glb_bounds_mm(MODEL_DIR / f"{self.plate.model}.glb")
    for got, want in zip(lo + hi, [0, 0, 0, 127.76, 85.48, 29.99]):
      self.assertAlmostEqual(got, want, delta=0.15)


if __name__ == "__main__":
  unittest.main()
