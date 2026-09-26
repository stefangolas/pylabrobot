"""Reading a `.glb`'s scene graph and bounds, and re-framing it, with the standard library only.

The viewer draws a model file in its resource's own frame: metres, Z up, the origin at the
resource's left-front-bottom corner. A file drawn elsewhere - Y up, as glTF defaults to, or with its
origin wherever the modelling tool left it - is brought into that frame by `reframe`, which adds a
single root node carrying the turn and the shift. The meshes' bytes are not touched.
"""

import json
import math
import struct
from typing import Any, Dict, List, Optional, Sequence, Tuple

Vec = Tuple[float, float, float]
Matrix = List[List[float]]

_MAGIC = b"glTF"
_JSON = 0x4E4F534A
_BIN = 0x004E4942


def read(path: str) -> Tuple[Dict[str, Any], bytes]:
  """A `.glb`'s JSON and its binary chunk."""
  with open(path, "rb") as f:
    data = f.read()
  magic, version, _ = struct.unpack_from("<4sII", data, 0)
  if magic != _MAGIC or version != 2:
    raise ValueError(f"{path} is not a glTF 2 binary")
  length, kind = struct.unpack_from("<II", data, 12)
  if kind != _JSON:
    raise ValueError(f"{path} does not start with its JSON")
  document = json.loads(data[20 : 20 + length])
  rest = 20 + length
  binary = b""
  if rest < len(data):
    bin_length, bin_kind = struct.unpack_from("<II", data, rest)
    if bin_kind == _BIN:
      binary = data[rest + 8 : rest + 8 + bin_length]
  return document, binary


def write(path: str, document: Dict[str, Any], binary: bytes) -> None:
  text = json.dumps(document, separators=(",", ":")).encode()
  text += b" " * (-len(text) % 4)
  body = struct.pack("<II", len(text), _JSON) + text
  if binary:
    binary += b"\0" * (-len(binary) % 4)
    body += struct.pack("<II", len(binary), _BIN) + binary
  with open(path, "wb") as f:
    f.write(struct.pack("<4sII", _MAGIC, 2, 12 + len(body)) + body)


def _multiply(a: Matrix, b: Matrix) -> Matrix:
  return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def _local(node: Dict[str, Any]) -> Matrix:
  """A node's own transform: its matrix, or translation x rotation x scale."""
  if "matrix" in node:
    m = node["matrix"]  # column-major
    return [[m[c * 4 + r] for c in range(4)] for r in range(4)]
  x, y, z, w = node.get("rotation", [0.0, 0.0, 0.0, 1.0])
  sx, sy, sz = node.get("scale", [1.0, 1.0, 1.0])
  tx, ty, tz = node.get("translation", [0.0, 0.0, 0.0])
  r = [
    [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
    [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
    [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
  ]
  return [
    [r[0][0] * sx, r[0][1] * sy, r[0][2] * sz, tx],
    [r[1][0] * sx, r[1][1] * sy, r[1][2] * sz, ty],
    [r[2][0] * sx, r[2][1] * sy, r[2][2] * sz, tz],
    [0.0, 0.0, 0.0, 1.0],
  ]


_IDENTITY: Matrix = [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]


def bounds(document: Dict[str, Any], root: Optional[Matrix] = None) -> Tuple[Vec, Vec]:
  """The smallest box, in the file's own units and axes, around the corners of every mesh's
  position bounds as the scene places them. Exact when the nodes only turn by quarter turns, shift
  and scale - as a file `reframe` has framed does - and a bound otherwise."""
  lo, hi = [math.inf] * 3, [-math.inf] * 3
  nodes = document.get("nodes", [])
  scene = document.get("scenes", [{}])[document.get("scene", 0)]

  def visit(index: int, parent: Matrix) -> None:
    node = nodes[index]
    world = _multiply(parent, _local(node))
    if "mesh" in node:
      for primitive in document["meshes"][node["mesh"]]["primitives"]:
        accessor = document["accessors"][primitive["attributes"]["POSITION"]]
        a, b = accessor["min"], accessor["max"]
        for corner in ((x, y, z) for x in (a[0], b[0]) for y in (a[1], b[1]) for z in (a[2], b[2])):
          p = [sum(world[i][k] * corner[k] for k in range(3)) + world[i][3] for i in range(3)]
          for k in range(3):
            lo[k], hi[k] = min(lo[k], p[k]), max(hi[k], p[k])
    for child in node.get("children", []):
      visit(child, world)

  for index in scene.get("nodes", []):
    visit(index, root or _IDENTITY)
  if lo[0] == math.inf:
    raise ValueError("the file has no mesh with position bounds")
  return (lo[0], lo[1], lo[2]), (hi[0], hi[1], hi[2])


# A quarter turn about X: what is up along Y comes up along Z, and what runs back along -Z runs
# back along +Y - three.js's convention of a Y-up scene with the front towards the viewer.
Y_UP_TO_Z_UP = [math.sqrt(0.5), 0.0, 0.0, math.sqrt(0.5)]


def reframe(document: Dict[str, Any], up: str, name: str) -> Vec:
  """Put the scene's content in the resource frame: turned Z up if `up` is "Y", and shifted so the
  corner of its bounds is the origin. Adds one root node named `name`; returns the shift."""
  if up not in ("Y", "Z"):
    raise ValueError(f"up must be Y or Z, not {up!r}")
  rotation = Y_UP_TO_Z_UP if up == "Y" else [0.0, 0.0, 0.0, 1.0]
  turned = _local({"rotation": rotation})
  (x, y, z), _ = bounds(document, turned)
  shift = (-x, -y, -z)
  scene = document.setdefault("scenes", [{}])[document.get("scene", 0)]
  nodes = document.setdefault("nodes", [])
  nodes.append(
    {"name": name, "rotation": rotation, "translation": list(shift), "children": scene["nodes"]}
  )
  scene["nodes"] = [len(nodes) - 1]
  return shift


def sizes(path: str) -> Vec:
  """How big the file's content is along each axis, in its own units."""
  (a, b) = bounds(read(path)[0])
  return (b[0] - a[0], b[1] - a[1], b[2] - a[2])


def corner(path: str) -> Vec:
  return bounds(read(path)[0])[0]


__all__: Sequence[str] = ["read", "write", "bounds", "reframe", "sizes", "corner"]
