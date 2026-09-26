"""Bring a `.glb` into the viewer's model frame and put it where the viewer finds it by name.

    python tools/import_glb.py SOURCE.glb pylabrobot/resources/<maker>/resource_model/<model>.glb --up Y

The viewer draws `<model>.glb`, found anywhere under the package, for every resource whose `model`
is `<model>`, in the resource's own frame: metres, Z up, the origin at its left-front-bottom
corner. This adds one root node turning the content Z up (if it was Y up) and shifting the corner of
its bounds to the origin; the meshes' bytes are copied as they are. Units are not converted: the
source must already be in metres.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from pylabrobot.visualizer3D import glb  # noqa: E402


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
  parser.add_argument("source")
  parser.add_argument("target")
  parser.add_argument("--up", choices=("Y", "Z"), required=True, help="the source's up axis")
  args = parser.parse_args()
  document, binary = glb.read(args.source)
  model = os.path.splitext(os.path.basename(args.target))[0]
  shift = glb.reframe(document, args.up, f"{model}_resource_frame")
  os.makedirs(os.path.dirname(os.path.abspath(args.target)), exist_ok=True)
  glb.write(args.target, document, binary)
  lo, hi = glb.bounds(glb.read(args.target)[0])
  size = [round((b - a) * 1000, 2) for a, b in zip(lo, hi)]
  print(
    f"{model}: shifted by {[round(s * 1000, 2) for s in shift]} mm; now {size} mm, corner at "
    f"{[round(v * 1000, 3) for v in lo]} mm"
  )


if __name__ == "__main__":
  main()
