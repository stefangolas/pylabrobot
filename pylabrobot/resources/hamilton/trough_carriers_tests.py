"""Hamilton's trough carriers against Hamilton's templates."""

import unittest

from pylabrobot.resources.hamilton.trough_carriers import Trough_CAR_5R60_A00


class TroughCarrier5R60Tests(unittest.TestCase):
  # RGT_CAR_5R60_A00.tml (Hamilton NGS STAR kits): 20 x 89.9 sites at X 1.25, Z 63.5, their fronts
  # at Y 6.5 + 96 i, front to back.
  TEMPLATE_Y = [6.5 + 96.0 * i for i in range(5)]

  def test_five_sites_on_the_templates_pitch(self):
    carrier = Trough_CAR_5R60_A00("car")
    self.assertEqual(len(carrier.sites), 5)
    for i, want in enumerate(self.TEMPLATE_Y):
      with self.subTest(site=i):
        site = carrier.sites[i]
        # measured, within half a millimetre of the template
        self.assertAlmostEqual(site.location.y, want, delta=0.5)
        self.assertAlmostEqual(site.location.z, 63.5, places=6)


if __name__ == "__main__":
  unittest.main()
