"""Fit how long a STAR's channel commands take, and test whether the channels move in Y one after
another, from Venus HxUsbComm traces.

    python tools/hxusbcomm_channels.py PATH [PATH ...] [--max-mb 900] [--command C0AS]

Every channel command (`C0 AS/DS/TP/TR`) is paired with the channel command just before it, when
nothing else moved in between and both answered without error. Only commands whose active channels
share one X are kept (a pick-up spread over several X columns is several passes). Each pair gives
the X distance, the eight channels' Y distances, the volume time (volume / flow, slowest channel),
the mixing time, and the Z stroke (traverse height to the liquid surface or tip height).

The duration is fit as a fixed-effects model

    d = a[group] + b_v * volume_time + b_m * mix_time + b_z * Tz + b_xy * Txy + e

where a group is the previous command plus every categorical parameter of this one (continuous ones
removed), so everything that does not vary within a group is absorbed. Txy is one of several
hypotheses about how X and the eight Y drives combine (X alone, Y together = the longest channel,
Y in sequence = the sum, max or sum of X and Y, a fixed overhead whenever Y moves, a stagger per
extra moving channel, and both). Nonlinear constants are found on a grid with the linear solve
inside. Each model is reported with its within-group R^2, RMS, AIC and BIC.

X uses the S-curve fitted by `hxusbcomm_timing.py` (600 mm/s, 1297 mm/s^2, 3210 mm/s^3), Y the
trapezoid from single-channel jogs (300 mm/s, 900 mm/s^2), Z PLR's 800 mm/s^2 with the speed gridded.
"""

import argparse
import collections
import json
import math
import os
import sys
from typing import Any, Dict, List

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hxusbcomm_timing import is_read, move_time, ok, pairs, trace_files  # noqa: E402

X_PROFILE = (600.0, 1297.0, 3210.0)
Y_PROFILE = (300.0, 900.0)
CHANNEL = ("C0AS", "C0DS", "C0TP", "C0TR")
MOVING_MM = 0.5  # Y positions jitter by 0.1 mm between commands; that is not a move
MIXING = {"mc", "mv", "mp", "ms", "mh"}
CONTINUOUS = {"av", "dv", "mv", "zl", "zx", "lp", "tp", "tz"}


def vals(s: str, n: int = 8) -> List[int]:
  """A per-channel field; a trailing `&` repeats the last value for the remaining channels."""
  if not s:
    return [0] * n
  rep = s.endswith("&")
  t = [int(x) for x in s.rstrip("&").split()]
  return (t + [t[-1] if rep else 0] * (n - len(t)))[:n]


def collect(files: List[str]) -> List[Dict[str, Any]]:
  out = []
  for path in files:
    prev = None
    for cmd, d, req, rep in pairs(path):
      if is_read(cmd):
        continue
      if cmd not in CHANNEL or "yp" not in req:
        prev = None  # something else may have moved
        continue
      tm = vals(req.get("tm", ""))
      act = [i for i in range(8) if tm[i]]
      xs = {x for i, x in enumerate(vals(req.get("xp", ""))) if i in act and x}
      e = {
        "c": cmd,
        "d": d,
        "ok": ok(rep),
        "y": vals(req["yp"]),
        "act": act,
        "p": req,
        "x": xs.pop() if len(xs) == 1 else None,
      }
      if (
        prev is not None
        and prev["ok"]
        and e["ok"]
        and e["x"] is not None
        and prev["x"] is not None
        and act
      ):
        out.append(row(prev, e))
      prev = e
  return out


def row(prev: Dict[str, Any], e: Dict[str, Any]) -> Dict[str, Any]:
  q, act, cmd = e["p"], e["act"], e["c"]
  volume, speed = {"C0AS": ("av", "as"), "C0DS": ("dv", "ds")}.get(cmd, (None, None))
  tv = 0.0
  if volume:
    v, s = vals(q.get(volume, "")), vals(q.get(speed, ""))
    tv = max((v[i] / s[i] for i in act if s[i]), default=0.0)
  mix = 0.0
  if q.get("mc", "00&") != "00&":
    mc, mv, ms = vals(q["mc"]), vals(q["mv"]), vals(q["ms"])
    mix = max((2 * mc[i] * mv[i] / ms[i] for i in act if ms[i]), default=0.0)
  z = vals(q.get("zl" if volume else "tp", ""))
  th = int(q.get("th", "2450"))
  # Mixing parameters are inert without mixing cycles; keeping them would split groups by protocol
  # and absorb effects (such as the Z stroke) that differ between protocols.
  inert = MIXING if not mix else set()
  key = (
    prev["c"]
    + q.get("tm", "")
    + json.dumps({k: v for k, v in q.items() if k not in CONTINUOUS | inert}, sort_keys=True)
  )
  return {
    "c": cmd,
    "key": key,
    "d": e["d"],
    "tv": tv,
    "mix": mix,
    "stroke": max((th - z[i]) / 10 for i in act),
    "dx": abs(e["x"] - prev["x"]) / 10,
    "dy": [abs(a - b) / 10 for a, b in zip(e["y"], prev["y"])],
  }


def fit(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
  cnt = collections.Counter(r["key"] for r in rows)
  rows = [r for r in rows if cnt[r["key"]] >= 5]
  keys = {k: i for i, k in enumerate(sorted({r["key"] for r in rows}))}
  K, n = len(keys), len(rows)
  g = np.array([keys[r["key"]] for r in rows])
  counts = np.bincount(g, None, K)

  def within(y: np.ndarray) -> np.ndarray:
    return y - (np.bincount(g, y, K) / counts)[g]

  d = within(np.array([r["d"] for r in rows]))
  sst = d @ d
  tv = np.array([r["tv"] for r in rows])
  mix = np.array([r["mix"] for r in rows])
  strokes = np.array([r["stroke"] for r in rows])
  tx = np.array([move_time(r["dx"], *X_PROFILE) for r in rows])
  ty = np.array([[move_time(v, *Y_PROFILE) for v in r["dy"]] for r in rows])
  tymax, tysum = ty.max(1), ty.sum(1)
  moving = (np.array([r["dy"] for r in rows]) > MOVING_MM).sum(1)
  ymove = (moving > 0).astype(float)
  extra = np.maximum(moving - 1, 0)

  def rss(cols: List[np.ndarray]) -> float:
    X = np.column_stack([within(c) for c in cols])
    b, *_ = np.linalg.lstsq(X, d, rcond=None)
    r = d - X @ b
    return float(r @ r)

  tz_speed = min(
    (50, 75, 100, 150, 200, 250, 300, 400),
    key=lambda v: rss([tv, mix, 2 * np.array([move_time(s, v, 800.0) for s in strokes])]),
  )
  tz = 2 * np.array([move_time(s, tz_speed, 800.0) for s in strokes])
  base = [tv, mix, tz]
  cs, ss = np.arange(0, 1.51, 0.05), np.arange(0, 0.31, 0.02)

  def best(f, grid):
    return min(grid, key=lambda p: rss(base + [f(*p)]))

  c1, _ = best(lambda c, s: np.maximum(tx, tymax + c * ymove), [(c, 0.0) for c in cs])
  _, s1 = best(lambda c, s: np.maximum(tx, tymax + s * extra), [(0.0, s) for s in ss])
  c2, s2 = best(
    lambda c, s: np.maximum(tx, tymax + c * ymove + s * extra), [(c, s) for c in cs for s in ss]
  )
  models = {
    "no XY": (None, 0),
    "X only": (tx, 0),
    "Y together (max)": (tymax, 0),
    "Y sequential (sum)": (tysum, 0),
    "max(X, Y together)": (np.maximum(tx, tymax), 0),
    "max(X, Y sequential)": (np.maximum(tx, tysum), 0),
    "X then Y together": (tx + tymax, 0),
    "X then Y sequential": (tx + tysum, 0),
    f"max(X, Y together + {c1:.2f} s when Y moves)": (np.maximum(tx, tymax + c1 * ymove), 1),
    f"max(X, Y together + {s1:.2f} s per extra channel)": (np.maximum(tx, tymax + s1 * extra), 1),
    f"max(X, Y together + {c2:.2f} s + {s2:.2f} s per extra channel)": (
      np.maximum(tx, tymax + c2 * ymove + s2 * extra),
      2,
    ),
  }
  out = {
    "_": {
      "rows": n,
      "groups": K,
      "z_speed": tz_speed,
      **{f"moving_{k}": int(v) for k, v in collections.Counter(moving.tolist()).items()},
    }
  }
  for name, (T, grid_k) in models.items():
    r = rss(base + ([T] if T is not None else []))
    k = K + len(base) + (T is not None) + grid_k
    out[name] = {
      "r2_within": 1 - r / sst,
      "rms_ms": 1000 * math.sqrt(r / n),
      "aic": n * math.log(r / n) + 2 * k,
      "bic": n * math.log(r / n) + k * math.log(n),
    }
  return out


def main() -> None:
  ap = argparse.ArgumentParser(
    description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
  )
  ap.add_argument("paths", nargs="+")
  ap.add_argument("--max-mb", type=float, default=900)
  ap.add_argument("--command", action="append", choices=CHANNEL)
  ap.add_argument("--out")
  args = ap.parse_args()
  rows = collect(trace_files(args.paths, args.max_mb * 1e6))
  report = {}
  for cmd in args.command or CHANNEL:
    res = fit([r for r in rows if r["c"] == cmd])
    report[cmd] = res
    print(f"{cmd}: {res['_']}")
    for name, m in res.items():
      if name != "_":
        print(
          f"  {name:52s} R2w {m['r2_within']:.4f}  RMS {m['rms_ms']:6.1f} ms  "
          f"AIC {m['aic']:12.1f}  BIC {m['bic']:12.1f}"
        )
  if args.out:
    with open(args.out, "w") as f:
      json.dump(report, f, indent=1)


if __name__ == "__main__":
  main()
