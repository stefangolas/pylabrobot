"""Checking that a run draws as smooth motion, without a browser.

    async with watched(viewer) as report:
      await pipettes.pick_up_tips(spots)
    assert_smooth(report)

`watched` starts a headless page in Node (`smoothness_page.mjs`) against a running viewer. The page
applies what the viewer sends as the real page does - the scene, state, moves and motions, played by
the page's own player - and samples where every resource is, `hz` times a second of motion and on
either side of every message. The run waits for it as it waits for any page, so the scenario runs at
the pace of the motion, `speed` times as fast as the drives. It reports:

- jumps: a step longer than anything could travel at `max_speed` in the time between two samples;
- strays: anything moving during a motion that the motion does not move - nothing it names, and
  nothing standing on what it names;
- snaps: anything moving outside a motion at all. Everything that moves should be acted out, so a
  snap is the model putting something somewhere with no motion to draw the way: a command the viewer
  does not read, or a motion that ends somewhere else than the model does;
- handovers: a tip, plate or lid that moved in being handed to a new holder - a shaft, a spot, a
  gripper, a site - rather than keeping where it was and then moving there;
- arrivals: a model update that finds the page anywhere but where it says - checked on every update,
  for every position and rotation in it, whether or not anything visibly moved;
- and, given the model, every resource at the end where the model has it, but what the page carried
  in a gripper itself.

The server says which commands it does not act out, so a snap is put down to the command behind it,
and `undecoded` lists the ones a scenario went through.
"""

import asyncio
import contextlib
import json
import os
import pathlib
import shutil
import tempfile
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional

from .server import Viewer3D

PAGE = pathlib.Path(__file__).parent / "smoothness_page.mjs"
NODE = shutil.which("node")


@dataclass
class Report:
  """What the headless page saw: how many samples and motions, and every jump."""

  samples: int = 0
  motions: int = 0
  motion_time: float = 0.0
  jumps: List[Dict[str, Any]] = field(default_factory=list)
  strays: List[Dict[str, Any]] = field(default_factory=list)
  snaps: List[Dict[str, Any]] = field(default_factory=list)
  handovers: List[Dict[str, Any]] = field(default_factory=list)
  arrivals: List[Dict[str, Any]] = field(default_factory=list)
  undecoded: List[str] = field(default_factory=list)
  carried: List[str] = field(default_factory=list)
  final: Dict[str, List[float]] = field(default_factory=dict)
  trace: str = ""


@contextlib.asynccontextmanager
async def watched(
  viewer: Viewer3D,
  hz: float = 20.0,
  speed: float = 4.0,
  max_speed: float = 600.0,
  slack: float = 1.5,
  floor: float = 1.0,
  ready_timeout: float = 60.0,
  trace: Optional[str] = None,
) -> AsyncIterator[Report]:
  """Watch a viewer with a headless page for the length of the block.

  Args:
    viewer: a started viewer, with `attach_motion` called if its motions are to be played.
    hz: samples per second of the drives' time.
    speed: how much faster than the drives the page plays.
    max_speed: the fastest anything on the device may move, in mm/s. A step longer than this allows
      for the time between two samples, times `slack`, plus `floor` mm, is a jump.
    slack: a factor on `max_speed`.
    floor: mm that any step may be, whatever the time.
    ready_timeout: how long to wait for the page to have the scene, in s.
    trace: a resource whose every change the page writes to stderr, kept in `Report.trace`.

  Raises:
    RuntimeError: If there is no Node, or the page never gets a scene.
  """
  if NODE is None:
    raise RuntimeError("the headless page runs in Node, and there is none on the path")
  handle, report_path = tempfile.mkstemp(suffix=".json", prefix="smoothness_")
  os.close(handle)
  config = {
    "hz": hz,
    "speed": speed,
    "maxSpeed": max_speed,
    "slack": slack,
    "floor": floor,
    "report": report_path,
  }
  if trace:
    config["trace"] = trace
  page = await asyncio.create_subprocess_exec(
    NODE,
    str(PAGE),
    viewer.ws_url,
    json.dumps(config),
    stdin=asyncio.subprocess.PIPE,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
  )
  assert page.stdin is not None and page.stdout is not None
  report = Report()
  try:
    line = await asyncio.wait_for(page.stdout.readline(), ready_timeout)
    if line.strip() != b"ready":
      error = (await page.stderr.read()).decode()[-2000:] if page.stderr else ""
      raise RuntimeError(f"the headless page did not get a scene: {line!r} {error}")
    yield report
  finally:
    if page.returncode is None:
      page.stdin.close()
      try:
        await asyncio.wait_for(page.wait(), 30)
      except asyncio.TimeoutError:
        with contextlib.suppress(ProcessLookupError):
          page.kill()
        await page.wait()
    if page.stderr is not None:
      report.trace = (await page.stderr.read()).decode(errors="replace")
    try:
      result = json.loads(pathlib.Path(report_path).read_text() or "null")
    finally:
      os.unlink(report_path)
    if result is not None:
      report.samples = result["samples"]
      report.motions = result["motions"]
      report.motion_time = result["motionTime"]
      report.jumps = result["jumps"]
      report.strays = result["strays"]
      report.snaps = result["snaps"]
      report.handovers = result["handovers"]
      report.arrivals = result["arrivals"]
      report.undecoded = result["undecoded"]
      report.carried = result["carried"]
      report.final = result["final"]


def _describe(kind: str, found: List[Dict[str, Any]]) -> List[str]:
  first: Dict[str, Dict[str, Any]] = {}
  for item in found:
    first.setdefault(item["name"], item)
  lines = [f"{len(found)} {kind} in {len(first)} resources:"]
  for item in list(first.values())[:8]:
    if "page" in item:
      off = f"{item['mm']} mm" if "mm" in item else f"{item['degrees']} degrees"
      lines.append(
        f"  {item['name']} [{item['category']}]: {item['kind']} after {item['after']} says "
        f"{item['model']}, page had {item['page']} ({off})"
      )
      continue
    if "landed" in item:
      lines.append(
        f"  {item['name']} [{item['category']}]: moved {item['mm']} mm in being handed to "
        f"{item['to']}, at t={item['t']} s: {item['from']} -> {item['landed']}"
      )
      continue
    if "model_at" in item:
      lines.append(
        f"  {item['name']} [{item['category']}]: ends at {item['page_at']} on the page, "
        f"{item['model_at']} in the model ({item['mm']} mm)"
      )
      continue
    limit = f" (allowed {item['allowed']})" if "allowed" in item else ""
    lines.append(
      f"  {item['name']} [{item['category']}]: {item['mm']} mm{limit} at t={item['t']} s, "
      f"after {item['after']}: {item['from']} -> {item['to']}"
    )
  return lines


def _against_model(report: Report, model: Any, tolerance: float) -> List[Dict[str, Any]]:
  """Every resource the page drew, where it ends against where the model has it.

  What the page carried in a gripper is left out, with what stands on it: the model never moves it.
  """
  carried = set(report.carried)
  found = []
  for resource in [model, *model.get_all_children()]:
    at = report.final.get(resource.name)
    if at is None:
      continue
    chain, skip = resource, False
    while chain is not None:
      if chain.name in carried:
        skip = True
        break
      chain = chain.parent
    if skip:
      continue
    where = resource.get_absolute_location()
    d = max(abs(at[0] - where.x), abs(at[1] - where.y), abs(at[2] - where.z))
    if d > tolerance:
      found.append(
        {
          "name": resource.name,
          "category": resource.category,
          "mm": round(d, 2),
          "page_at": at,
          "model_at": [round(where.x, 2), round(where.y, 2), round(where.z, 2)],
        }
      )
  return found


def assert_smooth(
  report: Report,
  ignore: Optional[List[str]] = None,
  allow_snaps: Optional[List[str]] = None,
  model: Any = None,
  tolerance: float = 0.25,
) -> None:
  """Raise if the page saw a jump, a stray, a snap or an arrival somewhere else, or, given the
  model, ended anywhere but where the model has things - naming the first few of each.

  Args:
    report: what `watched` reported.
    ignore: categories to leave out of every check.
    allow_snaps: categories that may move outside a motion: a part the viewer does not act out yet.
    model: the root the viewer was given, to compare where everything ends.
    tolerance: how far from the model a resource may end, in mm.
  """
  skipped = set(ignore or [])
  snapping = skipped | set(allow_snaps or [])
  if report.samples < 2:
    raise AssertionError("the headless page took too few samples to say anything")
  found = [
    ("jumps", [j for j in report.jumps if j["category"] not in skipped]),
    ("strays", [j for j in report.strays if j["category"] not in skipped]),
    ("snaps", [j for j in report.snaps if j["category"] not in snapping]),
    ("handovers that moved", [j for j in report.handovers if j["category"] not in skipped]),
    ("arrivals elsewhere", [j for j in report.arrivals if j["category"] not in snapping]),
  ]
  if model is not None:
    found.append(
      (
        "resources ending away from the model",
        [j for j in _against_model(report, model, tolerance) if j["category"] not in skipped],
      )
    )
  lines = [line for kind, items in found if items for line in _describe(kind, items)]
  if lines:
    header = f"over {report.samples} samples and {report.motions} motions"
    if report.undecoded:
      header += f", through commands not acted out: {', '.join(report.undecoded)}"
    header += ":"
    raise AssertionError("\n".join([header, *lines]))
