"""For tests that measure a resource against its model file."""

import json
import struct
from pathlib import Path


def glb_bounds_mm(path: Path):
  """Min and max corner (mm) over every POSITION accessor in a GLB, from its JSON chunk."""
  data = path.read_bytes()
  (length,) = struct.unpack("<I", data[12:16])
  gltf = json.loads(data[20 : 20 + length])
  accessors = [
    gltf["accessors"][p["attributes"]["POSITION"]]
    for mesh in gltf["meshes"]
    for p in mesh["primitives"]
  ]
  lo = [min(a["min"][i] for a in accessors) * 1000 for i in range(3)]
  hi = [max(a["max"][i] for a in accessors) * 1000 for i in range(3)]
  return lo, hi


def well_centre(plate, identifier: str):
  """A well's centre (x, y) in the plate's frame."""
  well = plate.get_well(identifier)
  assert well.location is not None
  return (well.location.x + well.get_size_x() / 2, well.location.y + well.get_size_y() / 2)
