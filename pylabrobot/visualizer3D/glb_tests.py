"""Model files: re-framing one, and the files shipped for PyLabRobot's own resources."""

import os
import tempfile
import unittest
from typing import Any, Callable, Dict, List, Tuple

from pylabrobot.resources.coordinate import Coordinate
from pylabrobot.resources.corning import cor_96_wellplate_360uL_Fb
from pylabrobot.resources.hamilton import PLT_CAR_L5AC_A00, TIP_CAR_480_A00
from pylabrobot.resources.resource import Resource
from pylabrobot.visualizer3D import glb
from pylabrobot.visualizer3D.server import Viewer3D
from pylabrobot.visualizer3D.server_tests import empty_facility


def one_box(lo, hi, **node: Any) -> Dict[str, Any]:
  """A document with one mesh whose positions span `lo` to `hi`, under one node."""
  return {
    "asset": {"version": "2.0"},
    "scene": 0,
    "scenes": [{"nodes": [0]}],
    "nodes": [{"mesh": 0, **node}],
    "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
    "accessors": [{"min": list(lo), "max": list(hi), "count": 8, "type": "VEC3"}],
  }


def close(a, b, tolerance=1e-9) -> bool:
  return all(abs(x - y) <= tolerance for x, y in zip(a, b))


class ReframeTests(unittest.TestCase):
  def test_a_y_up_file_comes_up_z_with_its_front_at_the_origin(self):
    # three.js's convention: up along Y, the back along -Z, the front edge at z = 0.
    document = one_box((0.0, -0.014, -0.497), (0.135, 0.1005, 0.0))
    shift = glb.reframe(document, "Y", "frame")
    lo, hi = glb.bounds(document)
    self.assertTrue(close(lo, (0, 0, 0)))
    self.assertTrue(close(hi, (0.135, 0.497, 0.1145)))
    self.assertTrue(close(shift, (0, 0, 0.014)))

  def test_a_z_up_file_is_only_shifted(self):
    document = one_box((-0.01, 0.02, 0.005), (0.1, 0.12, 0.05))
    glb.reframe(document, "Z", "frame")
    lo, hi = glb.bounds(document)
    self.assertTrue(close(lo, (0, 0, 0)))
    self.assertTrue(close(hi, (0.11, 0.1, 0.045)))

  def test_the_nodes_already_there_are_kept_under_the_new_one(self):
    document = one_box((0, 0, 0), (1, 1, 1), translation=[5.0, 0.0, 0.0])
    glb.reframe(document, "Z", "frame")
    self.assertEqual(document["scenes"][0]["nodes"], [1])
    self.assertEqual(document["nodes"][1]["children"], [0])
    self.assertTrue(close(glb.bounds(document)[0], (0, 0, 0)))

  def test_a_file_written_reads_back_the_same(self):
    document = one_box((0, 0, 0), (1, 2, 3))
    binary = bytes(range(10))
    with tempfile.TemporaryDirectory() as directory:
      path = os.path.join(directory, "m.glb")
      glb.write(path, document, binary)
      again, bytes_again = glb.read(path)
    self.assertEqual(again, document)
    self.assertEqual(bytes_again[:10], binary)


class ShippedModelTests(unittest.TestCase):
  """The files shipped for PyLabRobot resources are found by model name and sit in the resource's
  frame: their corner at its corner, their footprint its footprint. How tall each is drawn is
  recorded: a mesh drawn shorter than PyLabRobot's box changes nothing but the drawing."""

  CASES: List[Tuple[Callable[[str], Resource], float]] = [
    # (factory, drawn height in mm - PyLabRobot's box is 130 for both carriers)
    (PLT_CAR_L5AC_A00, 94.0),
    (TIP_CAR_480_A00, 114.5),
    (cor_96_wellplate_360uL_Fb, 14.0),
  ]

  def test_each_is_found_by_name_and_sits_in_its_resource_frame(self):
    facility = empty_facility()
    resources = []
    for k, (factory, _) in enumerate(self.CASES):
      resource: Resource = factory(f"r{k}")
      facility.assign_child_resource(resource, location=Coordinate(200.0 * k, 0, 0))
      resources.append(resource)
    viewer = Viewer3D(facility, open_browser=False)
    models = viewer._scene_message(rebuild=True)["models"]
    meshes = {m["model"]: m.get("mesh") for m in models if m.get("model")}
    for resource, (_, height) in zip(resources, self.CASES):
      with self.subTest(model=resource.model):
        mesh = meshes[resource.model]
        self.assertIsNotNone(mesh, f"{resource.model} is drawn as a box")
        path = viewer._mesh_files[mesh["url"][len("mesh/") :]]
        self.assertEqual(os.path.basename(path), f"{resource.model}.glb")
        lo, hi = glb.bounds(glb.read(path)[0])
        size = [(b - a) * 1000 for a, b in zip(lo, hi)]
        self.assertTrue(close([v * 1000 for v in lo], (0, 0, 0), 1e-6))
        self.assertLess(abs(size[0] - resource.get_size_x()), 0.5)
        self.assertLess(abs(size[1] - resource.get_size_y()), 0.5)
        self.assertAlmostEqual(size[2], height, places=3)
        self.assertLessEqual(size[2], resource.get_size_z())


if __name__ == "__main__":
  unittest.main()
