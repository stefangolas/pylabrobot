import unittest
from pathlib import Path

from pylabrobot.resources.coordinate import Coordinate
from pylabrobot.resources.corning import cor_96_wellplate_360uL_Fb
from pylabrobot.resources.biorad.plates_tests import glb_bounds_mm
from pylabrobot.resources.hamilton.heater_shakers import (
  HHS_RISER_HEIGHT,
  hamilton_heater_shaker,
  hamilton_heater_shaker_riser,
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

MODEL_DIR = Path(__file__).parent / "resource_model"
FLAT_MTP = (hamilton_hhs_nest_flat_mtp_2mm, hamilton_hhs_nest_flat_mtp_3mm)


def unit(name, nest_factory):
  """A Heater Shaker with a nest from `nest_factory`, on its riser if the nest needs one."""
  hhs = hamilton_heater_shaker(name, nest=nest_factory(f"{name}_nest"))
  return hamilton_heater_shaker_riser(f"{name}_riser", hhs) if nest_factory in FLAT_MTP else hhs


def nest_at(carrier, index):
  module = carrier.sites[index]
  hhs = module.resource if module.model == "hamilton_heater_shaker_riser" else module
  return hhs.nest


def site_on_carrier(carrier, index):
  """Where a plate lands on the nest at `index`, in the carrier's frame."""
  nest = nest_at(carrier, index)
  return nest.get_location_wrt(carrier) + nest.child_location


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
          carrier = hamilton_mfx_carrier_7T_shaker("car", modules={index: unit("hhs", factory)})
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
        3: unit("hhs1", hamilton_hhs_nest_flat_mtp_3mm),
        2: unit("hhs2", hamilton_hhs_nest_flat_mtp_3mm),
        1: unit("hhs3", hamilton_hhs_nest_flat_dwp_3mm),
      },
    )
    deck.assign_child_resource(carrier, location=Coordinate(1157.5, 63, 100))
    # The carrier's template sites, on top of where the layout put the carrier.
    expected = {3: (1172.75, 436.5, 212.7), 2: (1172.75, 316.5, 212.7), 1: (1172.75, 196.5, 183.0)}
    for index, (x, y, z) in expected.items():
      with self.subTest(index=index):
        nest = nest_at(carrier, index)
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

  def test_a_unit_on_its_riser_stands_where_hamiltons_model_draws_it(self):
    """In MFX_CAR_2HHSF30MTP_HHSF30DWP_CPAC.x the flat MTP units are centred like the others,
    raised by the riser."""
    carrier = hamilton_mfx_carrier_7T_shaker(
      "car", modules={2: unit("hhs", hamilton_hhs_nest_flat_mtp_3mm)}
    )
    hhs = carrier.sites[2].resource
    at = hhs.get_location_wrt(carrier)
    self.assertAlmostEqual(at.x + hhs.get_size_x() / 2, 78.75)
    self.assertAlmostEqual(at.y + hhs.get_size_y() / 2, 298.05)
    self.assertAlmostEqual(at.z, 8.0 + HHS_RISER_HEIGHT)


class ModelTests(unittest.TestCase):
  """Each model file drawn in its resource's frame (bounds in mm)."""

  BOUNDS = {
    # housing and clamps: the footprint at the foot, the clamp jaws 13 mm above the body
    "hamilton_heater_shaker": ([0, 0, 0], [147.12, 104.72, 85.9]),
    "hamilton_heater_shaker_riser": ([0, 0, 0], [148.0, 105.0, 29.0]),
    # nests: from the top of the unit's body, a Nunc nest reaching 1.6 mm into it
    "hamilton_hhs_nest_flat_dwp": ([2.31, 5.36, 0], [144.36, 99.36, 13.0]),
    "hamilton_hhs_nest_flat_mtp": ([2.31, 5.36, 0], [144.36, 99.36, 13.0]),
    "hamilton_hhs_nest_nunc_dwp": ([2.31, 5.36, -1.6], [144.36, 99.36, 29.5]),
    "hamilton_hhs_nest_sarstedt": ([2.31, 5.36, 0], [144.36, 99.36, 21.4]),
    "hamilton_hhs_nest_pcr96_abi": ([2.31, 5.36, 0], [144.36, 99.36, 13.0]),
    # 1.5 mm right of the template origin (Hamilton's 3DxOffset); the rear tab reaches 526.5
    "MFX_CAR_7T_shaker": ([1.5, 0, 0], [156.0, 526.5, 21.5]),
  }

  def test_every_model_is_in_its_resource_frame(self):
    for model, (lo, hi) in self.BOUNDS.items():
      with self.subTest(model=model):
        got_lo, got_hi = glb_bounds_mm(MODEL_DIR / f"{model}.glb")
        for got, want in zip(got_lo + got_hi, lo + hi):
          self.assertAlmostEqual(got, want, delta=0.01)

  def test_every_resource_has_its_model(self):
    carrier = hamilton_mfx_carrier_7T_shaker(
      "car",
      modules={
        0: unit("a", hamilton_hhs_nest_flat_mtp_2mm),
        1: unit("b", hamilton_hhs_nest_nunc_dwp_3mm),
        2: unit("c", hamilton_hhs_nest_sarstedt_1_5mm),
        3: unit("d", hamilton_hhs_nest_pcr96_abi),
      },
    )
    models = {r.model for r in carrier.get_all_children()} | {carrier.model}
    for model in models:
      with self.subTest(model=model):
        self.assertTrue((MODEL_DIR / f"{model}.glb").exists())


if __name__ == "__main__":
  unittest.main()
