import unittest

from pylabrobot.resources.coordinate import Coordinate
from pylabrobot.resources.corning import cor_96_wellplate_360uL_Fb
from pylabrobot.resources.hamilton.heater_shakers import (
  hamilton_heater_shaker,
  hamilton_hhs_nest_flat_dwp_2mm,
  hamilton_hhs_nest_flat_dwp_3mm,
  hamilton_hhs_nest_flat_mtp_2mm,
  hamilton_hhs_nest_flat_mtp_3mm,
  hamilton_hhs_nest_nunc_dwp_1_5mm,
  hamilton_hhs_nest_nunc_dwp_2mm,
  hamilton_hhs_nest_nunc_dwp_3mm,
  hamilton_hhs_nest_pcr96_abi,
  hamilton_hhs_nest_sarstedt_1_5mm,
)
from pylabrobot.resources.hamilton.mfx_carriers import hamilton_mfx_carrier_7T_shaker
from pylabrobot.resources.resource import Resource


def site_on_carrier(carrier, index):
  """Where a plate lands on the nest at `index`, in the carrier's frame."""
  hhs = carrier.sites[index]
  return hhs.location + hhs.nest.location + hhs.nest.child_location


class HeaterShakerOnShakerCarrierTests(unittest.TestCase):
  """Sites against Hamilton's own: the Multiflex catalogue and the Venus-assembled carriers."""

  # (nest, Venus site X, Y at Hamilton position 1, Z), from MultiMFX.INI; the 3 mm flat MTP,
  # 3 mm flat DWP and 3 mm Nunc DWP rows also equal the Venus-assembled carriers' templates.
  CASES = [
    (hamilton_hhs_nest_flat_mtp_2mm, 15.25, 374.0, 112.7),
    (hamilton_hhs_nest_flat_mtp_3mm, 15.25, 373.5, 112.7),
    (hamilton_hhs_nest_flat_dwp_2mm, 15.25, 374.0, 83.7),
    (hamilton_hhs_nest_flat_dwp_3mm, 15.25, 373.5, 83.0),
    (hamilton_hhs_nest_nunc_dwp_1_5mm, 15.25, 374.8, 83.25),
    (hamilton_hhs_nest_nunc_dwp_2mm, 15.25, 374.0, 83.0),
    (hamilton_hhs_nest_nunc_dwp_3mm, 15.25, 373.5, 83.0),
    (hamilton_hhs_nest_sarstedt_1_5mm, 15.25, 374.8, 79.3),
    (hamilton_hhs_nest_pcr96_abi, 15.25, 373.5, 91.2),
  ]

  def test_every_nest_on_every_position_lands_on_the_catalogue_site(self):
    for factory, x, y1, z in self.CASES:
      for index in range(4):
        with self.subTest(nest=factory.__name__, index=index):
          carrier = hamilton_mfx_carrier_7T_shaker(
            "car", modules={index: hamilton_heater_shaker(f"hhs{index}", nest=factory("nest"))}
          )
          site = site_on_carrier(carrier, index)
          position = 4 - index  # Hamilton counts from the back
          self.assertAlmostEqual(site.x, x, places=6)
          self.assertAlmostEqual(site.y, y1 - 120.0 * (position - 1), places=6)
          self.assertAlmostEqual(site.z, z, places=6)

  def test_the_roche_avenio_layout_places_its_plates_where_this_does(self):
    """Venus's `Avenio CGP.lay` puts MFX_CAR_2HHSF30MTP_HHSF30DWP_CPAC at deck (1157.5, 63, 100),
    with 3 mm flat MTP nests at positions 1 and 2 and a 3 mm flat DWP nest at 3."""
    deck = Resource("deck", size_x=2000, size_y=700, size_z=100)
    carrier = hamilton_mfx_carrier_7T_shaker(
      "car",
      modules={
        3: hamilton_heater_shaker("hhs1", nest=hamilton_hhs_nest_flat_mtp_3mm("n1")),
        2: hamilton_heater_shaker("hhs2", nest=hamilton_hhs_nest_flat_mtp_3mm("n2")),
        1: hamilton_heater_shaker("hhs3", nest=hamilton_hhs_nest_flat_dwp_3mm("n3")),
      },
    )
    deck.assign_child_resource(carrier, location=Coordinate(1157.5, 63, 100))
    # The carrier's template sites, on top of where the layout put the carrier.
    expected = {3: (1172.75, 436.5, 212.7), 2: (1172.75, 316.5, 212.7), 1: (1172.75, 196.5, 183.0)}
    for index, (x, y, z) in expected.items():
      with self.subTest(index=index):
        nest = carrier.sites[index].nest
        plate = cor_96_wellplate_360uL_Fb(f"plate{index}")
        nest.assign_child_resource(plate)
        at = plate.get_absolute_location()
        self.assertAlmostEqual(at.x, x, places=6)
        self.assertAlmostEqual(at.y, y, places=6)
        self.assertAlmostEqual(at.z, z, places=6)

  def test_a_unit_is_centred_in_its_slot_on_the_carrier_plate(self):
    carrier = hamilton_mfx_carrier_7T_shaker("car", modules={0: hamilton_heater_shaker("hhs")})
    hhs = carrier.sites[0]
    self.assertAlmostEqual(hhs.location.x + hhs.get_size_x() / 2, 78.75)
    self.assertAlmostEqual(hhs.location.y + hhs.get_size_y() / 2, 58.05)
    self.assertAlmostEqual(hhs.location.z, 8.0)


if __name__ == "__main__":
  unittest.main()
