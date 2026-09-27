"""Fit what a STAR's commands take beyond the motion the page draws, and the 96-head's and iSWAP's
travel, from Venus HxUsbComm traces.

    python tools/hxusbcomm_fixed.py PATH [PATH ...] [--max-mb 900] [--out fixed.json]

One pass over the traces. Three fits come out of it:

- Channels (`C0 AS/TP/TR`): each command, paired with the channel command before it, is timed as
  the page draws it (X on the fitted S-curve, the channels' Y at 300 mm/s and 900 mm/s^2 setting off
  0.118 s apart, Z at 150 mm/s and 800 mm/s^2, the aspiration's volume and settling time). What is
  left is the command's fixed time, fitted as a linear model of the parameters that plausibly set
  it (mixing, transport air, channel count, the tip press `tp - tz`).
- 96-head (`C0 EM/EP/ER` after another head command): time = a[group] + max(X, head Y) + Z, head Y
  and Z at PLR's head drive defaults or on a grid; the fixed time is what is left at PLR's defaults.
- iSWAP (`C0 PP/PR` after one another): time = a[target site and grip parameters] + X and Y travel,
  combined as max or as sum, Y on a grid; the fixed time is what is left.

Every model is reported with its R^2 (within groups where there are groups), RMS, AIC and BIC.
"""

import argparse
import collections
import itertools
import json
import math
import os
import sys
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hxusbcomm_timing import is_read, move_time, ok, pairs, trace_files  # noqa: E402

X = (600.0, 1297.0, 3210.0)
CHANNEL_Y = (300.0, 900.0)
CHANNEL_Z = (150.0, 800.0)
STAGGER = 0.118
HEAD_Y_PLR = (390.62, 546.88)
HEAD_Z_PLR = (85.0, 400.0)
MOVING_MM = 0.5
CHANNEL = {"C0AS", "C0DS", "C0TP", "C0TR"}
HEAD = {"C0EA", "C0ED", "C0EM", "C0EP", "C0ER"}
ISWAP = {"C0PP", "C0PR"}
FAR_X = 850.0  # iSWAP targets right of this take a longer path


def vals(s: str, n: int = 8) -> List[int]:
  """A per-channel field; a trailing `&` repeats the last value for the remaining channels."""
  if not s:
    return [0] * n
  rep = s.endswith("&")
  t = [int(x) for x in s.rstrip("&").split()]
  return (t + [t[-1] if rep else 0] * (n - len(t)))[:n]


def signed(p: Dict[str, str], key: str, sign: str) -> float:
  return int(p[key]) * (-1 if p.get(sign) == "1" else 1) / 10


def stats(y: np.ndarray, residual: np.ndarray, k: int, groups: int = 0) -> Dict[str, float]:
  n = len(y)
  rss = float(residual @ residual)
  sst = float(((y - y.mean()) ** 2).sum()) if not groups else float(y @ y)
  return {
    "n": n,
    "r2": 1 - rss / sst if sst else float("nan"),
    "rms_ms": 1000 * math.sqrt(rss / n),
    "aic": n * math.log(rss / n) + 2 * k,
    "bic": n * math.log(rss / n) + k * math.log(n),
  }


def z_time(d: float) -> float:
  return move_time(abs(d), *CHANNEL_Z)


# -- channels ---------------------------------------------------------------------------------------


def channel_row(prev: Dict[str, Any], e: Dict[str, Any]) -> Optional[Dict[str, Any]]:
  """The fixed time of one channel command, with the parameters that may set it."""
  q, act = e["p"], e["act"]
  tx = move_time(abs(e["x"] - prev["x"]) / 10, *X)
  dys = [abs(a - b) / 10 for a, b in zip(e["y"], prev["y"])]
  moving = [i for i in range(8) if dys[i] > MOVING_MM]
  ty = max((r * STAGGER + move_time(dys[i], *CHANNEL_Y) for r, i in enumerate(moving)), default=0.0)
  th = int(q.get("th", 2450)) / 10
  te = int(q.get("te", q.get("th", 2450))) / 10
  rise = z_time(th - prev["te"]) if prev["te"] < th else 0.0
  base = rise + max(tx, ty)
  i = act[0]
  if e["c"] == "C0AS":
    zl, ip, zx, av, sp, wt, de = (
      vals(q.get(k, "")) for k in ("zl", "ip", "zx", "av", "as", "wt", "de")
    )
    downs = {j: max(zl[j] - ip[j], zx[j]) / 10 for j in act}
    drawn = (
      base
      + max(z_time(th - downs[j]) for j in act)
      + max(av[j] / sp[j] + wt[j] / 10 for j in act if sp[j])
      + max((zl[j] / 10 - downs[j]) / (de[j] / 10) if de[j] else 0.0 for j in act)
      + max(z_time(te - zl[j] / 10) for j in act)
    )
    mc, mv, ms, ta = (vals(q.get(k, "")) for k in ("mc", "mv", "ms", "ta"))
    features = {
      "mix volume time": 2 * mc[i] * mv[i] / ms[i] if ms[i] and mc[i] else 0.0,
      "mix cycles": float(mc[i]),
      "transport air time": ta[i] / sp[i] if sp[i] else 0.0,
      "channels": float(len(act)),
    }
  elif e["c"] == "C0TP":
    tp, tz = vals(q.get("tp", "")), vals(q.get("tz", ""))
    drawn = (
      base + max(z_time(th - tz[j] / 10) for j in act) + max(z_time(te - tz[j] / 10) for j in act)
    )
    features = {"press tp-tz mm": (tp[i] - tz[i]) / 10, "channels": float(len(act))}
  elif e["c"] == "C0TR":
    tz = vals(q.get("tz", ""))
    drawn = (
      base + max(z_time(th - tz[j] / 10) for j in act) + max(z_time(te - tz[j] / 10) for j in act)
    )
    features = {"channels": float(len(act))}
  else:
    return None
  return {"c": e["c"], "fixed": e["d"] - drawn, "features": features}


def fit_linear(rows: List[Dict[str, Any]], names: Sequence[str]) -> Dict[str, Any]:
  y = np.array([r["fixed"] for r in rows])
  A = np.column_stack([np.ones(len(y))] + [[r["features"][n] for r in rows] for n in names])
  b, *_ = np.linalg.lstsq(A, y, rcond=None)
  r = y - A @ b
  cov = np.linalg.pinv(A.T @ A) * float(r @ r) / max(1, len(y) - A.shape[1])
  se = np.sqrt(np.clip(np.diag(cov), 0, None))
  return {
    "coefficients": {n: [float(v), float(s)] for n, v, s in zip(["constant", *names], b, se)},
    **stats(y, r, A.shape[1]),
  }


# -- 96-head and iSWAP: travel with a fixed effect per group ----------------------------------------


def within_fit(
  rows: List[Dict[str, Any]], travel: Callable[[Dict[str, Any]], float]
) -> Dict[str, float]:
  cnt = collections.Counter(r["key"] for r in rows)
  rows = [r for r in rows if cnt[r["key"]] >= 3]
  keys = {k: i for i, k in enumerate(sorted({r["key"] for r in rows}))}
  g = np.array([keys[r["key"]] for r in rows])
  counts = np.bincount(g, None, len(keys))

  def within(v: np.ndarray) -> np.ndarray:
    return v - (np.bincount(g, v, len(keys)) / counts)[g]

  d = within(np.array([r["d"] for r in rows]))
  t = within(np.array([travel(r) for r in rows]))
  return {"groups": len(keys), **stats(d, d - t, len(keys), groups=len(keys))}


def head_travel(r: Dict[str, Any], y: Tuple[float, float], z: Tuple[float, float]) -> float:
  across = max(move_time(r["dx"], *X), move_time(r["dy"], *y))
  return across + sum(move_time(v, *z) for v in (r["rise"], r["down"], r["up"]))


def iswap_travel(r: Dict[str, Any], y: Tuple[float, float], combine: str) -> float:
  tx, ty = move_time(r["dx"], *X), move_time(r["dy"], *y)
  return max(tx, ty) if combine == "max" else tx + ty


# -- one pass ----------------------------------------------------------------------------------------


def collect(files: List[str]) -> Tuple[List[Dict], List[Dict], List[Dict]]:
  channel, head, iswap = [], [], []
  for path in files:
    prev_channel = prev_head = prev_iswap = None
    for cmd, d, req, rep in pairs(path):
      if is_read(cmd):
        continue
      e = {"c": cmd, "d": d, "ok": ok(rep), "p": req}
      if cmd in CHANNEL and "yp" in req:
        tm = vals(req.get("tm", ""))
        e["act"] = [i for i in range(8) if tm[i]]
        xs = {x for i, x in enumerate(vals(req.get("xp", ""))) if i in e["act"] and x}
        e["x"] = xs.pop() if len(xs) == 1 else None
        e["y"] = vals(req["yp"])
        e["te"] = int(req.get("te", req.get("th", 2450))) / 10
        p = prev_channel
        if p and p["ok"] and e["ok"] and e["act"] and e["x"] is not None and p["x"] is not None:
          row = channel_row(p, e)
          if row:
            channel.append(row)
        prev_channel, prev_head, prev_iswap = e, None, None
      elif cmd in HEAD:
        p = prev_head
        need = ("xs", "yh", "zh", "za")
        if (
          p
          and p["ok"]
          and e["ok"]
          and cmd in ("C0EM", "C0EP", "C0ER")
          and all(k in req for k in need)
          and all(k in p["p"] for k in ("xs", "yh"))
        ):
          pp = p["p"]
          z0 = int(pp["za"] if p["c"] == "C0EM" else pp.get("ze", pp.get("za", 0))) / 10
          zh, za = int(req["zh"]) / 10, int(req["za"]) / 10
          ze = int(req.get("ze", req["za"])) / 10
          head.append(
            {
              "c": cmd,
              "d": d,
              "dx": abs(signed(req, "xs", "xd") - signed(pp, "xs", "xd")),
              "dy": abs(int(req["yh"]) - int(pp["yh"])) / 10,
              "rise": max(0.0, zh - z0),
              "down": abs(zh - za),
              "up": 0.0 if cmd == "C0EM" else abs(ze - za),
              "key": cmd
              + p["c"]
              + json.dumps(
                {k: v for k, v in req.items() if k not in ("xs", "yh", "xd")}, sort_keys=True
              ),
            }
          )
        prev_head, prev_channel, prev_iswap = e, None, None
      elif cmd in ISWAP:
        p = prev_iswap
        if p and p["ok"] and e["ok"]:
          pp = p["p"]
          try:
            iswap.append(
              {
                "c": cmd,
                "d": d,
                "dx": abs(signed(req, "xs", "xd") - signed(pp, "xs", "xd")),
                "dy": abs(signed(req, "yj", "yd") - signed(pp, "yj", "yd")),
                "far": signed(req, "xs", "xd") > FAR_X,
                "key": cmd
                + p["c"]
                + req["xs"]
                + "/"
                + req["yj"]
                + "/"
                + req["zj"]
                + json.dumps(
                  {k: req.get(k) for k in ("th", "te", "gw", "go", "gb", "gt", "ga", "gr")}
                )
                + str(pp.get("gr")),
              }
            )
          except KeyError:
            pass
        prev_iswap, prev_channel, prev_head = e, None, None
      else:
        prev_channel = prev_head = prev_iswap = None
  return channel, head, iswap


def report(channel: List[Dict], head: List[Dict], iswap: List[Dict]) -> Dict[str, Any]:
  out: Dict[str, Any] = {"channels": {}, "head96": {}, "iswap": {}}
  models = {
    "C0AS": ["mix volume time", "mix cycles", "transport air time"],
    "C0TP": ["press tp-tz mm"],
    "C0TR": ["channels"],  # reported to show it adds nothing
  }
  for cmd, names in models.items():
    rows = [r for r in channel if r["c"] == cmd]
    out["channels"][cmd] = {"constant only": fit_linear(rows, []), "model": fit_linear(rows, names)}

  for name, y, z in (("PLR defaults", HEAD_Y_PLR, HEAD_Z_PLR),):
    out["head96"][f"max(X, head Y) + Z, {name}"] = within_fit(head, lambda r: head_travel(r, y, z))
  best = min(
    itertools.product([300, 390.62, 500], [400, 546.88, 800, 1200, 1500]),
    key=lambda p: within_fit(head, lambda r: head_travel(r, p, HEAD_Z_PLR))["rms_ms"],
  )
  out["head96"][f"max(X, head Y {best[0]}, {best[1]}) + Z PLR"] = within_fit(
    head, lambda r: head_travel(r, best, HEAD_Z_PLR)
  )
  out["head96"]["X then head Y, PLR defaults"] = within_fit(
    head,
    lambda r: (
      move_time(r["dx"], *X)
      + move_time(r["dy"], *HEAD_Y_PLR)
      + sum(move_time(v, *HEAD_Z_PLR) for v in (r["rise"], r["down"], r["up"]))
    ),
  )
  for cmd in ("C0EM", "C0EP", "C0ER"):
    v = [r["d"] - head_travel(r, HEAD_Y_PLR, HEAD_Z_PLR) for r in head if r["c"] == cmd]
    if v:
      out["head96"][f"{cmd} fixed"] = {"median_s": float(np.median(v)), "n": len(v)}

  grid = list(itertools.product([150, 200, 250, 300, 400, 600], [200, 400, 800, 1200, 2000]))
  for cmd in ("C0PP", "C0PR"):
    rows = [r for r in iswap if r["c"] == cmd]
    for combine in ("max", "sum"):
      y = min(grid, key=lambda p: within_fit(rows, lambda r: iswap_travel(r, p, combine))["rms_ms"])
      out["iswap"][f"{cmd} {combine}(X, Y) Y {y}"] = within_fit(
        rows, lambda r: iswap_travel(r, y, combine)
      )
    for far in (False, True):
      v = [r["d"] - iswap_travel(r, (300.0, 800.0), "sum") for r in rows if r["far"] == far]
      if v:
        out["iswap"][f"{cmd} fixed, target X > {FAR_X:.0f} mm = {far}"] = {
          "median_s": float(np.median(v)),
          "n": len(v),
        }
  return out


def main() -> None:
  ap = argparse.ArgumentParser(
    description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
  )
  ap.add_argument("paths", nargs="+")
  ap.add_argument("--max-mb", type=float, default=900)
  ap.add_argument("--out")
  args = ap.parse_args()
  res = report(*collect(trace_files(args.paths, args.max_mb * 1e6)))
  print(json.dumps(res, indent=1))
  if args.out:
    with open(args.out, "w") as f:
      json.dump(res, f, indent=1)


if __name__ == "__main__":
  main()
