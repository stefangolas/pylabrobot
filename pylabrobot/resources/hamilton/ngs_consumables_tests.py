"""Consumables and fixtures from Hamilton's NGS STAR labware definitions, against those definitions."""

import unittest

from pylabrobot.resources import (
  Resource,
  biorad_96_wellplate_200uL_Vb,
  cor_axy_1_troughplate_300mL_Vb,
  eppendorf_tube_1500uL_Vb,
  hamilton_1_trough_20mL_Vb,
  hamilton_24_tuberack_eppendorf_1_5mL_adapter,
  hamilton_24_tuberack_gemx_adapter,
  hamilton_96_tip_support,
  hamilton_96_tiprack_300uL,
  hamilton_pcr_comfort_lid,
  hamilton_tip_300uL,
  hamilton_verification_block,
  roche_1_trough_20mL_Vb,
)


def centre_xy(resource, relative_to):
  at = resource.get_location_wrt(relative_to)
  return at.x + resource.get_size_x() / 2, at.y + resource.get_size_y() / 2


class ComfortLidTests(unittest.TestCase):
  def test_the_lid_sits_where_hamiltons_odtc_template_puts_it(self):
    plate = biorad_96_wellplate_200uL_Vb("plate")
    lid = hamilton_pcr_comfort_lid("lid")
    plate.assign_child_resource(lid)
    self.assertAlmostEqual(lid.get_location_wrt(plate).z, 12.0)  # Hamilton's ODTC lid site


class TubeAdapterTests(unittest.TestCase):
  def test_a_tube_stands_on_the_grid_with_its_floor_where_hamilton_puts_it(self):
    """A1 25.5 / 20.5 in from the left / back of Hamilton's 127 x 86, 15 mm pitch; floor 5.1."""
    rack = hamilton_24_tuberack_eppendorf_1_5mL_adapter("rack")
    for key, (x, y) in {"A1": (25.5, 86 - 20.5), "D6": (25.5 + 75, 86 - 20.5 - 45)}.items():
      with self.subTest(key=key):
        tube = eppendorf_tube_1500uL_Vb(f"tube_{key}")
        rack[key] = tube
        cx, cy = centre_xy(tube, rack)
        self.assertAlmostEqual(cx - (127.76 - 127) / 2, x, places=6)
        self.assertAlmostEqual(cy + (86 - 85.48) / 2, y, places=6)
        floor = tube.get_location_wrt(rack).z + tube.material_z_thickness
        self.assertAlmostEqual(floor, 5.1, places=6)

  def test_the_gemx_adapter_seats_each_tube_type_at_its_floor(self):
    rack = hamilton_24_tuberack_gemx_adapter("rack")
    for key, z in {"A1": 2.5, "A2": 2.5, "A3": 10.7, "B4": 2.5, "C5": 10.7, "D6": 10.7}.items():
      with self.subTest(key=key):
        self.assertAlmostEqual(rack.get_item(key).location.z, z)


class ReservoirTests(unittest.TestCase):
  def test_volume_and_height_are_inverse(self):
    for factory in (hamilton_1_trough_20mL_Vb, roche_1_trough_20mL_Vb):
      trough = factory("t")
      for volume in [100, 5000, 9235, 9236, trough.max_volume]:
        with self.subTest(trough=factory.__name__, volume=volume):
          height = trough.compute_height_from_volume(volume)
          self.assertAlmostEqual(trough.compute_volume_from_height(height), volume, places=6)

  def test_max_volumes(self):
    self.assertAlmostEqual(roche_1_trough_20mL_Vb("t").max_volume, 26516.3, delta=0.1)
    self.assertAlmostEqual(hamilton_1_trough_20mL_Vb("t").max_volume, 17962.7, delta=0.1)

  def test_the_axygen_reservoir_spans_the_96_grid(self):
    plate = cor_axy_1_troughplate_300mL_Vb("res")
    well = plate.get_well("A1")
    at = well.location
    self.assertAlmostEqual(at.x + 4.5, 14.38)  # A1's centre
    self.assertAlmostEqual(85.48 - (at.y + well.get_size_y() - 4.5), 11.24)
    self.assertAlmostEqual(well.compute_volume_from_height(38.58), 300_000, delta=100)


class TipSupportTests(unittest.TestCase):
  def test_a_tip_stands_higher_than_in_its_rack(self):
    rack = hamilton_96_tiprack_300uL("rack")
    for core_ii, raise_ in [(False, 11.5), (True, 15.3)]:
      with self.subTest(core_ii=core_ii):
        support = hamilton_96_tip_support("s", "300uL", hamilton_tip_300uL, core_ii=core_ii)
        rack_spot, support_spot = rack.get_item("A1").location, support.get_item("A1").location
        self.assertAlmostEqual(support_spot.x, rack_spot.x)
        self.assertAlmostEqual(support_spot.y, rack_spot.y)
        self.assertAlmostEqual(support_spot.z - rack_spot.z, raise_, places=6)

  def test_it_is_empty_until_filled(self):
    support = hamilton_96_tip_support("s", "1000uL", hamilton_tip_300uL)
    self.assertFalse(support.get_item("A1").has_tip())
    self.assertAlmostEqual(support.get_size_z(), 13.0)


class VerificationBlockTests(unittest.TestCase):
  def test_the_pocket(self):
    block = hamilton_verification_block("v")
    pocket = block.children[0]
    self.assertAlmostEqual(pocket.location.z, 23.0)
    self.assertEqual(centre_xy(pocket, block), (12.0, 15.0))

  def test_serialization_keeps_the_geometry(self):
    block = hamilton_verification_block("v")
    copy = Resource.deserialize(block.serialize())
    self.assertEqual(copy.children[0].location, block.children[0].location)


if __name__ == "__main__":
  unittest.main()
