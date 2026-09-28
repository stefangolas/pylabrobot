"""Hamilton's HP Tabbed nests on the L5 base, against Hamilton's NGS STAR carrier template."""

import unittest
from pathlib import Path

from pylabrobot.resources.biorad.plates_tests import glb_bounds_mm
from pylabrobot.resources.hamilton.mfx_carriers import (
  hamilton_mfx_carrier_L5_2MTP_MIDI_2DWP_HP_tabbed,
)
from pylabrobot.resources.thermo_fisher import thermo_TS_abgene_96_wellplate_800uL_Vb

MODEL_DIR = Path(__file__).parent / "resource_model"


class HPTabbedCarrierTests(unittest.TestCase):
  # `MFX_CAR_2MTP HPTab_MIDI HPTab_2DWP HPTab.tml` (NGS STAR MOA, KAPA HyperPlus): each site's
  # front-left corner (X, Y) and height, front to back.
  SITES = [(4, 8.5, 82.4), (4, 104.5, 82.4), (4, 200.5, 94.8), (4, 296.5, 109.7), (4, 392.5, 109.7)]

  def test_every_site_is_the_templates(self):
    carrier = hamilton_mfx_carrier_L5_2MTP_MIDI_2DWP_HP_tabbed("car")
    for index, (x, y, z) in enumerate(self.SITES):
      with self.subTest(index=index):
        module = carrier.sites[index]
        site = module.location + module.child_location
        self.assertAlmostEqual(site.x, x, places=6)
        self.assertAlmostEqual(site.y, y, places=6)
        self.assertAlmostEqual(site.z, z, places=6)

  def test_a_midi_plate_sits_on_the_midi_nest(self):
    carrier = hamilton_mfx_carrier_L5_2MTP_MIDI_2DWP_HP_tabbed("car")
    plate = thermo_TS_abgene_96_wellplate_800uL_Vb("midi")
    carrier.sites[2].assign_child_resource(plate)
    self.assertAlmostEqual(plate.get_location_wrt(carrier).z, 94.8, places=6)

  def test_the_models_are_in_the_module_frame(self):
    """Centred on the 135 x 94 module, the foot 0.2 below it (Hamilton's 18 vs PLR's 18.2), the
    corner tabs about 10.8 above the plate seat."""
    tops = {"MTP": 102.361, "DWP": 74.753, "MIDI": 87.302}
    for kind, top in tops.items():
      with self.subTest(kind=kind):
        lo, hi = glb_bounds_mm(MODEL_DIR / f"hamilton_mfx_plateholder_{kind}_HP_tabbed.glb")
        self.assertAlmostEqual((lo[0] + hi[0]) / 2, 67.5, delta=0.01)
        self.assertAlmostEqual((lo[1] + hi[1]) / 2, 47.0, delta=0.01)
        self.assertAlmostEqual(lo[2], -0.2, delta=0.01)
        self.assertAlmostEqual(hi[2], top, delta=0.01)


if __name__ == "__main__":
  unittest.main()
