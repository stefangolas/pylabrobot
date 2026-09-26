"""Fit a Hamilton STAR's drive motion profiles from Venus HxUsbComm traces.

    python tools/hxusbcomm_timing.py PATH [PATH ...] [--max-mb 900] [--out timing.json]

Each PATH is a trace file or a directory searched for `HxUsbComm*.trc`. A trace logs every firmware
command sent (`<`) and every reply (`>`) with a millisecond timestamp, so pairing them by id gives how
long each command took. Moves are isolated three ways:

- X-arm: pure X jogs (`C0 JX`; the 96-head's `C0 EM` when Y and Z are unchanged), and channel
  commands (`C0 AS/DS`) identical but for X with the channels still in Y. The X distance comes from
  the arm's last `C0 RX` read, else the previous command. Tip commands are left out: there, short X
  moves overlap the Z stroke and do not add to the time.
- Channel Y and Z: single-channel jogs (`C0 KY`, `C0 KZ`) from the previous jog of the same channel.

Within each group of otherwise identical commands, time = overhead + move(distance). The move is fit
as a trapezoid (speed, acceleration) and as a jerk-limited S-curve (speed, acceleration, jerk), with
one overhead per group, and compared by RMS, within-group R^2, AIC, AICc and BIC.

Traces are read one file at a time, so memory stays flat; `--max-mb` caps how much is read.
"""

import argparse
import collections
import itertools
import json
import math
import os
import re
import statistics
from typing import Any, Dict, Iterator, List, Optional, Tuple

LINE = re.compile(
  r"^(?P<dir>[<>]) (?P<h>\d\d):(?P<m>\d\d):(?P<s>\d\d)\.(?P<ms>\d{3}) (?P<dev>[^:]*): "
  r"(?P<mod>[A-Z][0-9A-Z])(?P<cmd>[A-Z]{2})id(?P<id>\d{4})(?P<rest>.*)$"
)
PARAM = re.compile(r"([a-z]{2})([^a-z]*)")
Point = Tuple[float, float, int]  # distance mm, median time s, samples


def params(rest: str) -> Dict[str, str]:
  out: Dict[str, str] = {}
  for key, value in PARAM.findall(rest):
    out.setdefault(key, value.strip())
  return out


def pairs(path: str) -> Iterator[Tuple[str, float, Dict[str, str], Dict[str, str]]]:
  """(module+command, duration s, request params, reply params) for each answered request."""
  pending: Dict[Tuple[str, str, str], Tuple[float, Dict[str, str]]] = {}
  day, last = 0.0, -1.0
  with open(path, "r", encoding="latin-1", errors="replace") as f:
    for raw in f:
      m = LINE.match(raw.rstrip("\r\n"))
      if not m:
        continue
      t = int(m["h"]) * 3600 + int(m["m"]) * 60 + int(m["s"]) + int(m["ms"]) / 1000 + day
      if t < last - 3600:  # past midnight
        day += 86400
        t += 86400
      last = t
      key = (m["dev"], m["mod"] + m["cmd"], m["id"])
      if m["dir"] == "<":
        pending[key] = (t, params(m["rest"]))
      else:
        sent = pending.pop(key, None)
        if sent is not None:
          yield m["mod"] + m["cmd"], t - sent[0], sent[1], params(m["rest"])


def trace_files(paths: List[str], max_bytes: float) -> List[str]:
  found = []
  for p in paths:
    if os.path.isdir(p):
      for root, _, names in os.walk(p):
        found += [os.path.join(root, n) for n in names if re.match(r"HxUsbComm.*\.trc$", n)]
    else:
      found.append(p)
  kept, total = [], 0
  for f in sorted(found):
    size = os.path.getsize(f)
    if total + size > max_bytes:
      break
    kept.append(f)
    total += size
  return kept


def ok(reply: Dict[str, str]) -> bool:
  return reply.get("er", "00/00")[:2] == "00"


def is_read(cmd: str) -> bool:
  return cmd[2] in "RQ" or cmd == "C0TT"


def first_x(p: Dict[str, str]) -> Optional[int]:
  for tok in p.get("xp", "").replace("&", " ").split():
    if int(tok):
      return int(tok)
  return None


def collect(files: List[str]) -> Dict[str, Dict[str, List[Point]]]:
  """Every group of moves, by axis: {axis: {group: [(distance, median time, n)]}}."""
  raw: Dict[str, Dict[str, Dict[float, List[float]]]] = {
    axis: collections.defaultdict(lambda: collections.defaultdict(list)) for axis in ("x", "y", "z")
  }
  channel = {"C0AS", "C0DS", "C0TP", "C0TR"}
  for path in files:
    arm_x: Optional[int] = None
    # The last command that moved something, its parameters, and whether it answered without error:
    # a move measured from a failed one would be measured from where the arm never went.
    prev: Optional[Tuple[str, Dict[str, str], bool]] = None
    jogs: Dict[Tuple[str, str], int] = {}
    for cmd, d, req, rep in pairs(path):
      if cmd == "C0RX":
        try:
          arm_x = int(rep.get("rx", ""))
        except ValueError:
          pass
        continue
      if is_read(cmd):
        continue
      if cmd in ("C0KY", "C0KZ") and ok(rep):
        axis, field = ("y", "yj") if cmd == "C0KY" else ("z", "zj")
        target = int(req[field])
        key = (cmd, req.get("pn", ""))
        if key in jogs and target != jogs[key]:
          raw[axis][cmd][round(abs(target - jogs[key]) / 10, 1)].append(d)
        jogs = {k: v for k, v in jogs.items() if k[0] == cmd}
        jogs[key] = target
        prev = (cmd, req, True)
        continue
      jogs = {}
      if cmd == "C0JX" and ok(rep) and prev is not None and prev[0] == "C0JX" and prev[2]:
        dist = abs(int(req["xs"]) - int(prev[1]["xs"])) / 10
        if dist:
          raw["x"]["C0JX"][round(dist, 1)].append(d)
      if cmd == "C0EM" and ok(rep) and prev is not None and prev[0] == "C0EM" and prev[2]:
        p = prev[1]
        if all(p.get(k) == req.get(k) for k in ("yh", "zh", "za")):
          sign = lambda q: -1 if q.get("xd") == "1" else 1  # noqa: E731
          dist = abs(int(req["xs"]) * sign(req) - int(p["xs"]) * sign(p)) / 10
          if dist:
            raw["x"]["C0EM"][round(dist, 1)].append(d)
      if cmd in channel and cmd not in ("C0TP", "C0TR") and ok(rep):
        x = first_x(req)
        if x is not None and prev is not None and prev[0] in channel and prev[2]:
          if prev[1].get("yp") == req.get("yp"):
            start = arm_x if arm_x is not None else first_x(prev[1])
            if start is not None and x != start:
              rest = {k: v for k, v in req.items() if k != "xp"}
              group = json.dumps(
                [cmd, rest, prev[0], prev[1].get("te") or prev[1].get("th")], sort_keys=True
              )
              raw["x"][group][round(abs(x - start) / 10)].append(d)
        arm_x = x
      elif cmd in channel:
        arm_x = first_x(req) if ok(rep) else None
      prev = (cmd, req, ok(rep))
  out: Dict[str, Dict[str, List[Point]]] = {}
  for axis, groups in raw.items():
    out[axis] = {}
    for group, bins in groups.items():
      pts = [(dx, statistics.median(ts), len(ts)) for dx, ts in sorted(bins.items())]
      # Enough distances to say something about the shape, and enough samples not to be noise; the
      # jogs are a few repeated distances, each many times.
      jog = group in ("C0JX", "C0EM", "C0KY", "C0KZ")
      if len(pts) >= (2 if jog else 3) and sum(n for _, _, n in pts) >= 8:
        out[axis][group] = pts
  return out


# -- profiles -----------------------------------------------------------------------------------


def ramp_time(v: float, a: float, j: float) -> float:
  """One ramp from rest to v, the acceleration limited to a and ramping at j."""
  if v >= a * a / j:
    return v / a + a / j
  return 2 * math.sqrt(v / j)


def move_time(d: float, vmax: float, a: float, j: float = math.inf) -> float:
  """Rest to rest over d: t_ramp(v) + d / v, v the cruise speed or the peak the distance allows."""
  if d <= 0:
    return 0.0
  if math.isinf(j):
    if d * a >= vmax * vmax:
      return d / vmax + vmax / a
    return 2 * math.sqrt(d / a)
  if d >= vmax * ramp_time(vmax, a, j):
    return ramp_time(vmax, a, j) + d / vmax
  lo, hi = 0.0, vmax
  for _ in range(60):
    mid = (lo + hi) / 2
    if mid * ramp_time(mid, a, j) < d:
      lo = mid
    else:
      hi = mid
  return ramp_time(hi, a, j) + d / hi


def rss(
  groups: Dict[str, List[Point]], v: float, a: float, j: float, shared: bool = False
) -> float:
  """Squared error with one overhead per group, or with one overhead shared by every group."""
  residuals = []
  for pts in groups.values():
    model = [move_time(d, v, a, j) for d, _, _ in pts]
    residuals.append([t - m for (_, t, _), m in zip(pts, model)])
  if shared:
    c = statistics.mean(r for rs in residuals for r in rs)
    return sum((r - c) ** 2 for rs in residuals for r in rs)
  return sum(sum((r - statistics.mean(rs)) ** 2 for r in rs) for rs in residuals)


def fit(
  groups: Dict[str, List[Point]], jerk: bool, shared: bool = False
) -> Tuple[float, Tuple[float, float, float]]:
  vs = [100.0, 150, 200, 250, 300, 400, 500, 600, 700, 800, 1000, 1200, 1500, 2000]
  accs = [100.0, 150, 200, 300, 400, 500, 700, 800, 900, 1000, 1500, 2000, 3000, 5000]
  js = [300.0, 500, 1000, 1500, 2000, 3000, 4000, 6000, 10000, 20000] if jerk else [math.inf]
  best: Tuple[float, Tuple[float, float, float]] = min(
    ((rss(groups, *p, shared), p) for p in itertools.product(vs, accs, js)), key=lambda b: b[0]
  )
  for _ in range(4):  # refine around the best
    _, (v0, a0, j0) = best
    steps = (0.85, 0.93, 1.0, 1.07, 1.15)
    grid = itertools.product(
      [v0 * f for f in steps],
      [a0 * f for f in steps],
      [j0 * f for f in steps] if jerk else [math.inf],
    )
    best = min([best] + [(rss(groups, *p, shared), p) for p in grid], key=lambda b: b[0])
  return best


def compare(groups: Dict[str, List[Point]]) -> Dict[str, Dict[str, Optional[float]]]:
  n = sum(len(p) for p in groups.values())
  within = sum(
    sum((t - statistics.mean(tt for _, tt, _ in pts)) ** 2 for _, t, _ in pts)
    for pts in groups.values()
  )
  out = {}
  models = (
    ("trapezoid, one shared delay", False, True),
    ("s_curve, one shared delay", True, True),
    ("trapezoid, overhead per group", False, False),
    ("s_curve, overhead per group", True, False),
  )
  for name, jerk, shared in models:
    r, (v, a, j) = fit(groups, jerk, shared)
    k = (1 if shared else len(groups)) + (3 if jerk else 2)
    aic = n * math.log(r / n) + 2 * k
    out[name] = {
      "speed": v,
      "acceleration": a,
      "jerk": None if math.isinf(j) else j,
      "rms_ms": 1000 * math.sqrt(r / n),
      "within_group_r2": 1 - r / within if within else float("nan"),
      "aic": aic,
      "aicc": aic + 2 * k * (k + 1) / (n - k - 1) if n - k - 1 > 0 else float("nan"),
      "bic": n * math.log(r / n) + k * math.log(n),
      "points": n,
      "groups": len(groups),
    }
  return out


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
  parser.add_argument("paths", nargs="+")
  parser.add_argument("--max-mb", type=float, default=900.0)
  parser.add_argument("--out", default=None)
  args = parser.parse_args()
  files = trace_files(args.paths, args.max_mb * 1e6)
  data = collect(files)
  report: Dict[str, Any] = {"files": len(files), "axes": {}}
  for axis, groups in data.items():
    usable = {g: p for g, p in groups.items() if len(p) >= 2}
    if sum(len(p) for p in usable.values()) <= len(usable) + 3:
      report["axes"][axis] = {"groups": {g: p for g, p in usable.items()}, "fit": None}
      continue
    report["axes"][axis] = {"groups": usable, "fit": compare(usable)}
  for axis, r in report["axes"].items():
    print(f"== {axis}: {len(r['groups'])} groups")
    for name, f in (r["fit"] or {}).items():
      jerk = f"  j {f['jerk']:.0f}" if f["jerk"] else ""
      print(
        f"  {name:30s} v {f['speed']:.0f}  a {f['acceleration']:.0f}{jerk}  RMS {f['rms_ms']:.1f} ms"
        f"  R2 {f['within_group_r2']:.4f}  AIC {f['aic']:.1f}  AICc {f['aicc']:.1f}  BIC {f['bic']:.1f}"
      )
  if args.out:
    with open(args.out, "w") as f:
      json.dump(report, f, indent=1)


if __name__ == "__main__":
  main()
