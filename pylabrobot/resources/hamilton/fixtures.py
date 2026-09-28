"""Small Hamilton deck fixtures."""

from pylabrobot.resources.container import Container
from pylabrobot.resources.coordinate import Coordinate
from pylabrobot.resources.resource import Resource


def hamilton_verification_block(name: str) -> Resource:
  """Hamilton's verification block (Venus core labware 'Verification'; used by the 10x Genomics
  Chromium GEM-X protocol): a 30 x 30 x 35 block with a 14 x 14 pocket, 10 deep, its floor 23 above
  the block's bottom, centred 12 from the block's left and 15 from its back.
  """
  block = Resource(
    name=name,
    size_x=30.0,
    size_y=30.0,
    size_z=35.0,
    category="verification_block",
    model=hamilton_verification_block.__name__,
  )
  pocket = Container(
    name=f"{name}_pocket", size_x=14.0, size_y=14.0, size_z=10.0, max_volume=14.0 * 14.0 * 10.0
  )
  block.assign_child_resource(pocket, location=Coordinate(12.0 - 7.0, 30.0 - 15.0 - 7.0, 23.0))
  return block
