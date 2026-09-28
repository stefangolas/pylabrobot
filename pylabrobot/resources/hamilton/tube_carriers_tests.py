import os
import unittest

from pylabrobot.resources.hamilton.tube_carriers import (
  hamilton_tube_carrier_32_a00,
  hamilton_tube_carrier_32_a00_insert_eppendorf_1_5mL,
)

MODEL_DIR = os.path.join(os.path.dirname(__file__), "resource_model")


class TubeCarrier32Tests(unittest.TestCase):
  """The bare SMP_CAR_32_A00 (173410), as Hamilton's rack file and mesh give it."""

  def setUp(self):
    self.carrier = hamilton_tube_carrier_32_a00("carrier")

  def test_32_bores_on_the_rack_files_axes(self):
    self.assertEqual(len(self.carrier.sites), 32)
    for i, site in self.carrier.sites.items():
      centre = site.location + site.get_anchor("c", "c", "b")
      self.assertAlmostEqual(centre.x, 13.6)
      self.assertAlmostEqual(centre.y, 14.5 + 15 * i)
      self.assertAlmostEqual(centre.z, 9.85)  # the bore floor in the mesh
      self.assertAlmostEqual(site.get_size_x(), 13.5)

  def test_it_is_not_the_insert_variant(self):
    insert = hamilton_tube_carrier_32_a00_insert_eppendorf_1_5mL("insert")
    self.assertNotEqual(self.carrier.model, insert.model)
    self.assertNotAlmostEqual(
      self.carrier.sites[0].location.x + self.carrier.sites[0].get_size_x() / 2,
      insert.sites[0].location.x + insert.sites[0].get_size_x() / 2,
    )

  def test_its_model_file_is_where_the_viewer_finds_it(self):
    self.assertTrue(os.path.isfile(os.path.join(MODEL_DIR, f"{self.carrier.model}.glb")))


if __name__ == "__main__":
  unittest.main()
