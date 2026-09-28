"""Hamilton's ODTC carrier against its template (MFX_CAR_ODTC_MTP.tml), and the ODTC's cover."""

import asyncio
import unittest
from pathlib import Path

from pylabrobot.legacy.thermocycling.chatterbox import ThermocyclerChatterboxBackend
from pylabrobot.legacy.thermocycling.inheco import inheco_odtc
from pylabrobot.resources import biorad_96_wellplate_200uL_Vb, hamilton_pcr_comfort_lid
from pylabrobot.resources.biorad.plates_tests import glb_bounds_mm
from pylabrobot.resources.hamilton.mfx_carriers import hamilton_mfx_carrier_7T_odtc

HERE = Path(__file__).parent


def site_corner(resource, carrier, size=(127.0, 86.0)):
  """Where the template's 127 x 86 site would start, for a resource centred on it."""
  at = resource.get_location_wrt(carrier)
  return (
    at.x + resource.get_size_x() / 2 - size[0] / 2,
    at.y + resource.get_size_y() / 2 - size[1] / 2,
    at.z,
  )


class ODTCCarrierTests(unittest.TestCase):
  def setUp(self):
    self.odtc = inheco_odtc("odtc", ThermocyclerChatterboxBackend())
    self.carrier = hamilton_mfx_carrier_7T_odtc("car", self.odtc)

  def assertSite(self, got, want):
    for g, w in zip(got, want):
      self.assertAlmostEqual(g, w, places=6)

  def test_a_plate_in_the_odtc_is_on_site_1_odtc(self):
    plate = biorad_96_wellplate_200uL_Vb("plate")
    self.odtc.assign_child_resource(plate)
    self.assertSite(site_corner(plate, self.carrier), (15.25, 158.8, 94.5))

  def test_its_lid_is_on_site_2_odtc_lid(self):
    plate = biorad_96_wellplate_200uL_Vb("plate")
    self.odtc.assign_child_resource(plate)
    lid = hamilton_pcr_comfort_lid("lid")
    plate.assign_child_resource(lid)
    self.assertSite(site_corner(lid, self.carrier), (15.25, 158.8, 106.5))

  def test_a_parked_lid_is_on_site_3_mfx(self):
    lid = hamilton_pcr_comfort_lid("lid")
    self.carrier.sites[0].assign_child_resource(lid)
    self.assertSite(site_corner(lid, self.carrier), (15.25, 14.1, 107.0))

  def test_the_odtc_stands_centred_on_the_carrier_plate(self):
    at = self.odtc.get_location_wrt(self.carrier)
    self.assertAlmostEqual(at.x + self.odtc.get_size_x() / 2, 157.5 / 2)
    self.assertAlmostEqual(at.z, 8.0)


class ODTCCoverTests(unittest.TestCase):
  def test_the_cover_follows_the_lid_commands(self):
    odtc = inheco_odtc("odtc", ThermocyclerChatterboxBackend())
    updates = []
    odtc.register_state_update_callback(lambda state: updates.append(state))
    self.assertIsNone(odtc.cover_open)
    self.assertEqual(odtc.serialize_state()["joints"], {"cover_slide": 0.0})

    async def run():
      await odtc.setup()
      await odtc.close_lid()
      closed = odtc.serialize_state()["joints"]["cover_slide"]
      await odtc.open_lid()
      return closed

    self.assertEqual(asyncio.run(run()), -101.0)
    self.assertTrue(odtc.cover_open)
    self.assertEqual(odtc.serialize_state()["joints"], {"cover_slide": 0.0})
    self.assertGreaterEqual(len(updates), 2)

  def test_the_model_declares_the_cover_joint(self):
    odtc = inheco_odtc("odtc", ThermocyclerChatterboxBackend())
    self.assertTrue(Path(odtc.mesh["path"]).is_file())
    joint = odtc.mesh["joints"]["cover_slide"]
    self.assertEqual(
      (joint["node"], joint["type"], joint["axis"]), ("heated_cover", "prismatic", "y")
    )


class ModelTests(unittest.TestCase):
  def test_the_lid_park_model_is_in_its_frame(self):
    lo, hi = glb_bounds_mm(HERE / "resource_model" / "hamilton_mfx_odtc_lid_park.glb")
    for got, want in zip(lo + hi, [0, 0, 0, 134.3, 100.0, 104.0]):
      self.assertAlmostEqual(got, want, delta=0.01)


if __name__ == "__main__":
  unittest.main()
