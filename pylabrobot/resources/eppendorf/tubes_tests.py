"""The Eppendorf 1.5 mL tube's model against the tube resource."""

import unittest
from pathlib import Path

from pylabrobot.resources.biorad.plates_tests import glb_bounds_mm
from pylabrobot.resources.eppendorf import eppendorf_tube_1500uL_Vb

MODEL_DIR = Path(__file__).parent / "resource_model"


class EppendorfTubeModelTests(unittest.TestCase):
  def test_the_model_stands_in_the_tube_frame(self):
    """Tube axis on the footprint's centre, bottom at 0; the cap, modelled open, overhangs to +X
    and rises above the tube's 38.9 mm body."""
    tube = eppendorf_tube_1500uL_Vb("tube")
    lo, hi = glb_bounds_mm(MODEL_DIR / f"{tube.model}.glb")
    self.assertAlmostEqual(lo[2], 0.0, delta=0.01)
    # the rim collar is 12.8 across, centred on the axis: -1.48 .. 11.33 in Y
    self.assertAlmostEqual((lo[1] + hi[1]) / 2, tube.get_size_y() / 2, delta=0.01)
    self.assertAlmostEqual(hi[1] - lo[1], 12.81, delta=0.01)
    self.assertGreater(hi[2], tube.get_size_z())


if __name__ == "__main__":
  unittest.main()
