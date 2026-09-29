"""Hamilton's plate stacking carriers against Hamilton's templates (ML_STAR library)."""

import unittest

from pylabrobot.resources import ResourceStack
from pylabrobot.resources.biorad import biorad_96_wellplate_200uL_Vb
from pylabrobot.resources.hamilton import plate_carriers
from pylabrobot.resources.thermo_fisher import thermo_TS_abgene_96_wellplate_800uL_Vb


class StackingCarrierTests(unittest.TestCase):
  # PLT_CAR_L4ST_*.tml: four 127 x 86 sites at X 15.25, Y 52 + 107 i, front to back, at these
  # heights above the carrier's bottom. The preloaded variants share their carrier's sites.
  HEIGHTS = {
    "PLT_CAR_L4ST_B00": 18.0,
    "PLT_CAR_L4ST_B00_4x5_Nunc96": 18.0,
    "PLT_CAR_L4ST_C00": 86.0,
    "PLT_CAR_L4ST_HIGH_A00": 73.0,
    "PLT_CAR_L4ST_HIGH_A00_4x5_Nunc96": 73.0,
    "PLT_CAR_L4ST_LOW_A00": 18.0,
    "PLT_CAR_L4ST_LOW_A00_4x9_Nunc96": 18.0,
  }

  def test_every_site_is_the_templates(self):
    for factory, z in self.HEIGHTS.items():
      carrier = getattr(plate_carriers, factory)("car")
      for i in range(4):
        with self.subTest(factory=factory, site=i):
          site = carrier.sites[i]
          self.assertEqual(
            (site.location.x, site.location.y, site.location.z), (15.25, 52.0 + 107 * i, z)
          )

  def test_stacks_keep_hamiltons_pitch(self):
    """KAPA HyperPlus's deck stacks three MIDI plates and five Hard-Shells on PLT_CAR_L4ST (the
    low one): bottoms 28.75 and 12.25 apart, from 18 above the carrier's bottom."""
    carrier = plate_carriers.PLT_CAR_L4ST_LOW_A00("car")
    midis = ResourceStack(
      "midis", "z", [thermo_TS_abgene_96_wellplate_800uL_Vb(f"m{i}") for i in range(3)]
    )
    hsps = ResourceStack("hsps", "z", [biorad_96_wellplate_200uL_Vb(f"h{i}") for i in range(5)])
    carrier.sites[3].assign_child_resource(midis)
    carrier.sites[0].assign_child_resource(hsps)
    self.assertAlmostEqual(midis.get_top_item().get_location_wrt(carrier).z, 18 + 2 * 28.75)
    self.assertAlmostEqual(hsps.get_top_item().get_location_wrt(carrier).z, 18 + 4 * 12.25)


if __name__ == "__main__":
  unittest.main()
