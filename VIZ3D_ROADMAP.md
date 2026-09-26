# Visualizer3D motion, iSWAP/CO-RE transport and collision checking: intent, work and roadmap

Branch `viz3d-motion`, built on PyLabRobot PR [#1378](https://github.com/PyLabRobot/pylabrobot/pull/1378) (`Visualizer3D`, head `ffd8d3db5`). This document covers:
- what the work is for, and what it deliberately does not do;
- what exists, what is planned, and why the pivotal choices were made;
- every hardcoded quantity the work adds, with its source;
- how to split the work into small, standalone commits for review.

Per-command motion detail is in [`pylabrobot/visualizer3D/MOTION_PROFILES.md`](pylabrobot/visualizer3D/MOTION_PROFILES.md).

---

## 1. Intent

**The goal: a simulated STAR, drawn in 3D, that moves the way the machine moves, driven by what PyLabRobot actually sends.**

PR #1378 draws a PyLabRobot resource tree and redraws it whenever the model changes. A model update says where things *end up*, not how they got there. A tip pick-up, for example, shows up as channels jumping. The robot itself decides how to get there from the firmware commands it receives. This work adds that missing layer: each firmware command the driver sends is decoded into the drive targets it implies, and the page plays them as timed motion. The model stays the source of truth, and each model update must find the page already at the position it reports.

Alongside, three pieces the motion work needed and which are useful on their own:
- **Plate and lid moves planned in Python** from the iSWAP's primitive moves, instead of the firmware's compound commands. The planning is inspectable and overridable, and it updates the resource tree when the jaws grip and release.
- **CO-RE grip tool pick-up and return** for the v1 STAR driver, which could not do it before.
- **Collision checking** of planned motion, cheap enough to run before every move: what moves is swept and checked against what stands still.

### Scope
- The Hamilton STAR / STARlet through the v1 driver (`pylabrobot/hamilton/star/driver`), in its simulator. Nothing here needs hardware to run or test.
- The browser draws; Python plans, decides and checks. Every check runs headless (a Node page, no browser) so it can run in CI.

### Not in scope
- Replacing PR #1378's scene, meshes or state model.
- Reproducing firmware-internal motion that isn't documented (the compound plate commands, initialisation, park paths). Where we must show such motion, the choice is marked as a heuristic (section 5).
- Changing any PyLabRobot datum, except to fix one that contradicts the others. The CO-RE holder X (section 3.4) is the only case.

### Principles
1. **The resource model is the truth.** Animation is derived; the harness fails any run whose drawing does not end where the model is.
2. **Use a command's own parameters first.** Speeds, heights and targets come from the firmware parameters. Driver defaults come second, and a heuristic only when neither exists, marked as such.
3. **Every non-obvious number has a source.** Tags: FW / PLR / SIM / DOC / HEUR (section 6).
4. **Fixed, known-safe heights.** Travel heights never depend on what is on the deck. Collisions are checked separately, never avoided by computing a height from the deck.
5. **Headless verification**, generically: a harness asserts smoothness, stray motion, snaps and arrivals for any scenario.

---

## 2. How it works

```
PLR call ──► v1 STAR driver ──► firmware command ──► STARSimulationDriver._send
                                                        │  motion_listener(module, command, params)
                                                        ▼
                                 motion.star_motion()  → drive targets for the page
                                                        │  (Viewer3D: broadcast "motion", wait for
                                                        │   every page's "motion_done")
                                                        ▼
page: motion_player.js plays the phases, each move on motion_profile.js's trapezoid
                                                        │
simulator answers ──► model updated ──► "state"/"moves" ──► page already there (checked)
```

The iSWAP transport and the CO-RE tool commands are ordinary PLR calls. They reach the page through the same path, one primitive command at a time.

---

## 3. Existing work (committed on `viz3d-motion`)

| Area | What | Main files | Tests |
|---|---|---|---|
| 3.1 Motion channel | Driver hook; server broadcasts motion, waits for pages (120 s cap); holds back pre-recorded state; flushes the scene before a motion | `hamilton/star/driver/simulator.py` (`motion_listener`), `visualizer3D/server.py`, `static/motion.js`, `static/transport.js`, `static/app.js` | `motion_tests.py` (server) |
| 3.2 Profile and player | Trapezoid profile; phased player (rise → across → down → handover/dwell → leave → up; head moves; joint turns; jaws) | `static/motion_profile.js`, `static/motion_player.js` | `motion_player_tests.mjs` (21) |
| 3.3 Decoders | Channels `C0 TP/TR/AS/JY/JZ/FY/ZA`, X-arm `X0 XP/SP`, iSWAP `R0 YA/ZA/PA/GA` + `C0 GC`, 96-head `C0 EP/ER` + `H0 YA/ZA`, CO-RE `C0 ZT/ZS` | `visualizer3D/motion.py` | `motion_tests.py` (16) |
| 3.4 CO-RE grip tools | v1 `pick_up_core_gripper_tools` / `return_core_gripper_tools` / `core_gripper_tools()`; channels with a tool refuse tips; travel height counts the tool; holder `channel_x_center`; STAR "on waste" holder X fix; legacy X from the same datum (wire unchanged) | `features/pipettes.py`, `master.py`, `simulator.py`, `resources/hamilton/core_grippers.py`, `star_decks.py`, legacy `STAR_backend.py` | `core_gripper_tools_tests.py` (8), `hamilton_deck_tests.py` |
| 3.5 Carry on the page | Plates and lids the iSWAP grips ride the gripper; a lid set on a lidless plate becomes its lid | `static/carry.js`, `static/live.js` | player + harness |
| 3.6 iSWAP transport | `iSWAPTransport`: inverse kinematics per elbow stop, sweep-safe travel order, lid-skirt rule, legacy grip defaults, placement as PLR places; tree updated at grip/release | `features/iswap_transport.py` | `iswap_transport_tests.py` (8); 36/40 plate×direction combinations round-trip exactly, the other 4 are unreachable and refused |
| 3.7 Collision checking | Solids from the tree; bounding-volume tree over what stands still; convex sweeps; GJK distance; time-sliced checks between moving groups; iSWAP plan sweeps | `resources/collision.py`, `features/iswap_collisions.py` | `collision_tests.py` (19), `iswap_collisions_tests.py` (8) |
| 3.8 Smoothness harness | Headless page samples the scene at 20 Hz. Checks: jumps, strays (motion outside the expected movers), snaps, handovers, arrivals, final pose vs the model, undecoded commands | `smoothness.py`, `smoothness_page.mjs` | `smoothness_tests.py` (16 tests: scenarios and negative controls) |
| 3.9 Models | Three GLBs brought from threejs_visualizer into the viewer's frame (Z-up, corner origin) by one added root node, mesh bytes unchanged; importer tool | `visualizer3D/glb.py`, `tools/import_glb.py`, `resources/*/resource_model/*.glb`, `pyproject.toml` | `glb_tests.py` (5) |
| 3.10 Docs and demos | Per-command motion reference; demos | `MOTION_PROFILES.md`, `motion_demo.py`, `iswap_demo.py`, `transport_demo.py` | — |
| 3.11 View | Isometric start view from the front-left; framing on the root's children | `static/renderer.js`, `static/app.js` | — |

Findings recorded along the way:
- **STARlet "on waste" CO-RE holder:** the tools were 19.5 mm right of where the channels take them (817.0, beyond the 800.2 mm X travel). This came from #1342 centring the tools in the holder without moving the holder. It is fixed in 3.4.
- **Quarter-turned plates overlap their neighbours.** PLR places a plate turned 90° onto a landscape carrier site, where it overlaps the next site by ≈32 mm. The collision check reports it.
- **v1 STAR has no dispense in this PR.**
- **The page's tip overhang comes from a simulator-only method** (see 4.1).

---

## 4. Planned work, in order

| # | Work | Why / size | Depends on |
|---|---|---|---|
| 4.1 | Decoder overhang from the model (`TipMountingShaft.tip_bottom`), not `SimulatedPipettes._below_stop_disc` | Bug: on hardware, heights with a tip would be off by the tip length. Small | — |
| 4.2 | `C0 AS` surface following (`fp` over the dwell), transport-air pull-out (`po`), immersion direction (`it`), conical second section | Matches the device. Small | — |
| 4.3 | Cheap moves: `C0 KX/KR` (Z safety then X), `Px ZA`, `C0 JE` (even spread), `C0 JP` (post-answer targets) | Frequent commands. Small | 4.4 for `JP` |
| 4.4 | **Post-answer targets** in the motion channel, then detection searches `Px ZL/ZE/ZH`, `C0 XL`, `Px YL`, `H0 ZL`: a slow descent per channel, each stopping at its own detected height | Distinct, visible motion; the targets are known only from the answer. Medium | — |
| 4.5 | 96-head `H0 PA/PB` (stroke with dwell), `C0 EM` | Coverage. Small | — |
| 4.6 | CO-RE gripper plate transport (the paddles carry a plate), analogous to `iSWAPTransport`, with collision sweeps | Feature. Medium | 3.4 |
| 4.7 | Generic collision check of *decoded* motions (any command, not only iSWAP plans) | Reuses the decoder output. Medium | 3.7 |
| 4.8 | Planner ranks elbow configurations by collisions; refuse drops whose placement overlaps a neighbour | Found problems 2 and 3 of section 3. Small | 3.7 |
| 4.9 | Liquid drawn as a surface (height from `Container.compute_height_from_volume`), lowered over the dwell; the tip column rises | Visual fidelity. Medium | 4.2 |
| 4.10 | Dispense (`C0 DS`) and side touch, once v1 has dispense | Blocked upstream | v1 dispense |
| 4.11 | Park `C0 PG`, autoload, initialisation | Undocumented; heuristic, marked | — |
| 4.12 | Model validator (spatial facts with sources; AI-drafted parametric models, e.g. the 96-head) | Proposal (earlier notes, section 10a) | 3.9 |
| 4.13 | Validation on hardware: transport ordering, CO-RE X fix, timing | Needs a STAR | — |

---

## 5. Pivotal design choices, and why

1. **Animate from firmware commands, not from model changes.** A model change says where things end, never how they got there. Different commands can produce the same final state with different motion (tip pick-up vs a plain Z move). Only the command carries speeds, ordering and intermediate heights. Tweening state differences would re-implement the firmware's model anyway, with less information.
2. **Python waits on the animation.** PyLabRobot is asyncio. Blocking each command until every page reports it has played paces a simulated run to the drawing with no extra timing model. The 120 s cap keeps a stuck page from hanging a run.
3. **The page must already be where the model says.** Every model update is checked against the page (0.11 mm / 0.11°). Commands whose targets the simulator writes *before* the command is sent (`C0 FY`, `C0 ZA`, iSWAP moves) are marked `recorded_first`: their state is held back, so the page doesn't jump ahead of its own animation.
4. **Plan plate moves from primitives instead of compound commands.** The firmware's `C0 PP/PR/PM` "choos[es] among multiple valid poses unpredictably" ([discuss.pylabrobot.org/t/517/1](https://discuss.pylabrobot.org/t/intro-to-epic-tame-the-iswap/517/1)), and their internal motion isn't public. Planning in Python makes every step visible, overridable and drawable, and the tree can be updated exactly when the jaws grip and release.
5. **One fixed travel height; collisions checked, never avoided by computing heights.** A height worked out from the deck hides collisions instead of reporting them, and it makes motion depend on what happens to be on the deck. The iSWAP travels at its own `default_minimum_traverse_height` (284 mm). Collision checking is a separate pass that reports.
6. **Only moving things are checked against still ones, with convex sweeps.** No all-against-all checks. Straight moves and moves on independent axes are swept exactly as convex hulls. Turns are cut into arcs, each grown by a proven curvature bound (|p''| ≤ Δe²|a| + (Δe+Δw)²|b|, deviation ≤ max|p''|/8), which gave ≈30× fewer segments than a naive bound. Two moving groups are compared only over shared time slices.
7. **The page's speed profile matches the simulator's timing model** (a symmetric trapezoid, `SimulatedPipettes._get_travel_time`). The drawing and the simulated clock agree. The real drives' ramp shape isn't public.
8. **Handovers seat instead of snapping.** A tip changes parent where it stands, then moves to where the model will place it at the Z drive's pace. The small geometric difference between the stroke's bottom and the model's placement becomes motion, not a jump.
9. **Solids come from the tree by rule, not by list.** A leaf is solid. An itemized resource is solid whole. Something hanging outside its parent is solid. A frame (children inside it) is solid only below the lowest thing it holds. Enclosures are declared (`hollow`). This handles decks, carriers, arms and tools without per-type tables, at the cost of box-level fidelity (see 4.12).

---

## 6. Every hardcoded quantity this work adds

Tags:
- **FW**: from the firmware command.
- **PLR**: a PyLabRobot value or model.
- **SIM**: the PLR simulator's model.
- **DOC**: an external post.
- **HEUR**: ours, with a stated reason.

Values the page takes from commands and driver defaults (channel speeds, head and iSWAP drive defaults, tip heights) are in `MOTION_PROFILES.md` section 0 and are not repeated here.

### 6.1 Motion (decoder, player, server)
| Constant | Value | File | Tag | Source / justification |
|---|---|---|---|---|
| `X_SPEED`, `X_ACCELERATION` | 400 mm/s, 500 mm/s² | `motion.py` | HEUR | The v1 driver states no X rate (only an acceleration level); threejs_visualizer's values. |
| `SPOT_TOLERANCE` | 1.0 mm | `motion.py` | HEUR | Matching a command's XY to a tip spot: well above the 0.1 mm firmware resolution, far below the 9 mm pitch. |
| `TIP_DROP` | 1 | `motion.py` | FW / PLR | `ti=1` is DROP (`TipDropMethod`); DROP heights are the stop disc's (`_unchecked_fw_drop_tips` docstring). |
| Finger speed | half the jaw drive's | `motion.py` `_jaws` | derived | Symmetric jaws: each finger travels half the width change in the same time. |
| `STILL` | 0.05 mm | `motion_player.js` | HEUR | Below the 0.1 mm firmware resolution. |
| `MOTION_TIMEOUT_S` | 120 s | `server.py` | HEUR | Longest plausible single command; keeps a stuck page from hanging a run. |
| Start view | direction (−0.8, −1, 1.25) | `renderer.js` | HEUR (UX) | Isometric from the front-left, looking down. |

### 6.2 Page carry rules
| Constant | Value | File | Tag | Source / justification |
|---|---|---|---|---|
| `REACH` | 2 mm | `carry.js` | HEUR | A grip point may lie this far outside a box and still count as in it (rounding in stated sizes). |
| `DROP` | 30 mm | `carry.js` | HEUR | Highest above a site a plate may be released and still land on it. |
| `SUNK` | 10 mm | `carry.js` | HEUR | How far a site's surface may stand above the plate's bottom. PLR seats plates 3.03 mm into the demo carriers' sites (`PLT_CAR_L5AC_A00` placement). |

### 6.3 iSWAP transport
| Constant | Value | File | Tag | Source / justification |
|---|---|---|---|---|
| `GRIPPER_FACING` | front 90°, right 180°, back −90°, left 0° | `iswap_transport.py` | PLR + DOC | The grip direction is the side of the plate the wrist is on. Firmware numbering: "1 = negative Y, 2 = positive X, 3 = positive Y, 4 = negative X" (legacy `STARBackend` iSWAP docstrings). "Gripper facing you" pairs with `grip_direction="back"` ([docs/user_guide/hamilton/star/hardware/replacing-iswap.md](docs/user_guide/hamilton/star/hardware/replacing-iswap.md) step 14). Deck angles are PLR's `GRIPPER_DECK_DIRECTIONS`. |
| `ELBOW_STOPS` | left −180°, front −90°, right 0° (link 1's deck angle) | `iswap_transport.py` | PLR + DOC | Elbow drive −90/0/+90 = left/front/right ([discuss.pylabrobot.org/t/517/1](https://discuss.pylabrobot.org/t/intro-to-epic-tame-the-iswap/517/1)); link deck angle = drive − 90 (PLR `iSWAP` kinematics). |
| `OPEN_MARGIN`, `WIDTH_TOLERANCE`, `GRIP_STRENGTH`, `PICKUP_DISTANCE_FROM_TOP` | 3 mm, 2 mm, 4, 5 mm | `iswap_transport.py` | PLR | Legacy `STARBackend.pick_up_resource` defaults. |
| `BELOW_LID` | 2 mm | `iswap_transport.py` | HEUR | Grip a lidded plate this far below the lid's skirt (`Lid.nesting_z_height`, PLR) so the jaws close on the plate. |
| `SWEEP_SAMPLES` | 36 | `iswap_transport.py` | HEUR | A turn is checked every ≤10° of a full turn against `_check_pose_reachable`. |
| Travel height | `default_minimum_traverse_height` = 284 mm | `iswap_transport.py` | PLR | v1 iSWAP configuration; legacy sends 280 mm. |

### 6.4 CO-RE grip tools
| Constant | Value | File | Tag | Source / justification |
|---|---|---|---|---|
| `CORE_GRIPPER_TIP_TYPE_INDEX` | 14 | `pipettes.py` (moved from `master.py`) | PLR | Firmware tip type 14, cat. 186100 (`hamilton_core_gripper_tool` docstring; legacy `hamilton/base.py`). |
| `CORE_TOOL_PICK_UP_BEGIN/END_BELOW_TOP` | 0 / 10 mm | `pipettes.py` | PLR | Legacy `pick_up_core_gripper_tools`: begin 235, end 225, against tool tops at 235.0 (probed; `hamilton_core_gripper_1000ul_5ml_on_waste`). |
| `CORE_TOOL_RETURN_BEGIN/END_BELOW_TOP` | 20 / 30 mm | `pipettes.py` | PLR | Legacy `return_core_gripper_tools`: begin 215, end 205. |
| `channel_x_center` ("on waste") | 19.5 mm (39 / 2) | `core_grippers.py` | PLR | "left outer edge of rack is 19.5mm" (holder factory); the channels take the tools at the probed 797.5 / 1337.5 mm (PR #1276; legacy wire `xs07975`, `STAR_tests.py`). |
| Holder placement | x = probed − `channel_x_center`; y = 125 − 18 − 21.5; z = 200.5 | `star_decks.py` | PLR | Probed values from PR #1276; only the X reference changed. |

### 6.5 Collision checking
| Constant | Value | File | Tag | Source / justification |
|---|---|---|---|---|
| `CONTACT` | 0.05 mm | `collision.py` | HEUR | Every solid is drawn in by this much, so resting contact isn't a collision; about the rounding of stated sizes. |
| `turning(step=…)` | 5° default | `collision.py` | HEUR | Arc length for generic turns; the slack grows the hull, so the result is conservative at any step. |
| `TURN_SLACK` | 0.5 mm | `iswap_collisions.py` | HEUR | Most any point may stray from the checked hulls during a turn. |
| `CARRIED_REACH` | 150 mm | `iswap_collisions.py` | HEUR | Bound on how far carried parts reach past the grip centre (fingers, a plate's half-diagonal ≈ 77 mm). Only sets how finely turns are cut; errs large. |
| `ENCLOSURES` | `left_extension_housing` | `iswap_collisions.py` | PLR + HEUR | PLR's model puts the 96-head inside the housing whenever the arm is far left (`hamilton/star/device.py`), so the housing is an enclosure, not a solid. |
| GJK tolerances | 1e-9 relative, 64 iterations | `collision.py` | HEUR | Standard numerical guards. |

### 6.6 Smoothness harness
| Constant | Value | File | Tag | Source / justification |
|---|---|---|---|---|
| Sampling rate | 20 Hz | `smoothness.py` / `smoothness_page.mjs` | HEUR | Fine enough for a trapezoid at the speeds used; cheap in Node. |
| Speed limit for a jump | 600 mm/s × 1.5 slack + 1 mm floor | `smoothness_page.mjs` | HEUR | Above the fastest drive drawn (X, 400 mm/s). |
| `ARRIVAL_MM` / `ARRIVAL_DEG` | 0.11 mm / 0.11° | `smoothness_page.mjs` | HEUR | Just above the 0.1 mm firmware resolution. |
| Final pose tolerance | 0.25 mm | `smoothness.py` `assert_smooth` | HEUR | End-of-run model comparison, allowing rounding across a chain of parents. |
| `FRAME_S`, `KEEP` | 1/60 s, 500 | `smoothness_page.mjs` | HEUR | Page frame step; cap on findings kept in a report. |

### 6.7 Demos only (not library behaviour)
`iswap_demo.py`: `PLATE_GRIP_HEIGHT` 4 mm, `LID_GRIP_HEIGHT` 5 mm, `SQUEEZE` 3 mm (HEUR). This demo drives the primitives by hand; `transport_demo.py` uses `iSWAPTransport` instead.

---

## 7. Splitting the work into reviewable commits

The branch history grew as work went on, so several files were touched by several commits. For review, the series should be rebuilt from the final tree as small commits. Each passes its own tests and makes sense alone. Two stacks:

### Stack A: plain PyLabRobot, independent of PR #1378 (can go to `main`)
| # | Commit | Files (hunks) | Depends | Size |
|---|---|---|---|---|
| A1 | `HamiltonCoreGrippers.channel_x_center`; STAR "on waste" holder placed by its centre; legacy X from the datum (wire unchanged) | `resources/hamilton/core_grippers.py`, `star_decks.py`, legacy `STAR_backend.py` (`_get_core_x`), `hamilton_deck_tests.py` | — | ~40 lines |
| A2 | v1 STAR: pick up and return the CO-RE grip tools; `get_mounted_tool`; travel height counts tools | `features/pipettes.py`, `master.py` (constant import), `simulator.py` (ZT/ZS hunks), `core_gripper_tools_tests.py` | A1 | ~450 |
| A3 | Simulator: iSWAP `C0 GC` records the jaw width | `simulator.py` (SimulatedISWAP hunk) + a test | — | ~10 |
| A4 | Simulator: 96-head `C0 EP/ER` place the head; aspiration records the arm's X | `simulator.py` (SimulatedHead96 and aspirate hunks) + tests | — | ~60 |
| A5 | Simulator: `motion_listener` hook on the driver's send | `simulator.py` (driver hunk) + test | — | ~20 |
| A6 | Collision checking | `resources/collision.py`, `collision_tests.py` | — | ~940 |
| A7 | iSWAP transport from primitives | `features/iswap_transport.py`, `iswap_transport_tests.py` | (A3 for exact jaw state) | ~850 |
| A8 | iSWAP plan collision sweeps | `features/iswap_collisions.py`, `iswap_collisions_tests.py` | A6, A7 | ~480 |

### Stack B: on top of PR #1378
| # | Commit | Files (hunks) | Depends | Size |
|---|---|---|---|---|
| B1 | Motion channel: broadcast, wait for pages, hold-back, scene flush | `visualizer3D/server.py`, `static/motion.js`, `static/transport.js`, `static/app.js` (wiring) + server tests | A5 | ~300 |
| B2 | Profile and player | `static/motion_profile.js`, `static/motion_player.js`, `motion_player_tests.mjs` | — | ~720 |
| B3 | Channel decoders (`TP/TR/AS/JY/JZ/FY/ZA`, `X0 XP/SP`) | `motion.py` (channel part), `static/live.js` (setAxis/readAxis), `motion_tests.py` (channel tests) | B1, B2 | ~600 |
| B4 | iSWAP decoders and the page carry (lids included) | `motion.py` (iSWAP part), `static/carry.js`, `static/live.js` (turnTo/reattach), tests | B3, A3 | ~450 |
| B5 | 96-head decoders | `motion.py` (head part), tests | B3, A4 | ~200 |
| B6 | CO-RE `C0 ZT/ZS` decoders | `motion.py` (CO-RE part), a smoothness scenario | B3, A2 | ~80 |
| B7 | Smoothness harness | `smoothness.py`, `smoothness_page.mjs`, `smoothness_tests.py` (scenarios for B3–B6; transport scenarios after A7) | B3 | ~1000 |
| B8 | Start view and framing | `static/renderer.js`, `static/app.js` (`sceneBounds`) | — | ~30 |
| B9 | Models and importer | `visualizer3D/glb.py`, `glb_tests.py`, `tools/import_glb.py`, 3 GLBs, `pyproject.toml` glob | — | ~290 + binaries |
| B10 | Demos | `motion_demo.py`, `iswap_demo.py`, `transport_demo.py` | B3–B6, A7 | ~310 |
| B11 | Motion reference | `MOTION_PROFILES.md` | B3–B6 | doc |

How to rebuild the series:
- Start a branch at `ffd8d3db5` (PR head), or at `main` for stack A.
- For each commit, check out only its files from `viz3d-motion`. Files shared between commits need their hunks split: `simulator.py` (A2/A3/A4/A5), `motion.py` (B3–B6), `live.js` (B3/B4), `smoothness_tests.py` (B7 by scenario).
- Run that commit's test files, one at a time.
- Keep each message to what it changes and why, matching PyLabRobot's style.

Reviewer notes worth putting up front:
- **A1 fixes a live datum** (the model had the tools out of the arm's reach) without changing anything sent to the device.
- **The GLBs in B9 add 0.97 MB,** 0.68 MB of it the plate. Compressing them with Draco would cut this. Their provenance and license need confirming before upstreaming.
- **The iSWAP ordering (A7) and the CO-RE X fix (A1)** are validated in the simulator only.

---

## 8. Sources
- PyLabRobot forum: [Tame the iSWAP, post 1](https://discuss.pylabrobot.org/t/intro-to-epic-tame-the-iswap/517/1), [post 4](https://discuss.pylabrobot.org/t/intro-to-epic-tame-the-iswap/517/4); [surface following, post 6](https://discuss.pylabrobot.org/t/hamilton-surface-following-issues/304/6); [z-touch firmware, post 3](https://discuss.pylabrobot.org/t/reason-behind-z-touch-only-being-available-to-8-channels-made-in-2022-and-onwards/543/3).
- labautomation.io (Hamilton staff): [side touch, post 6](https://labautomation.io/t/post-dispense-tip-touch-on-starlet/2255/6), [post 9](https://labautomation.io/t/post-dispense-tip-touch-on-starlet/2255/9); [touch-off on the MPH, post 2](https://labautomation.io/t/touch-off-with-mph/1788/2); [Transport Paths Editor](https://labautomation.io/t/transport-paths-editor/5759).
- PyLabRobot PRs: [#1378 Visualizer3D](https://github.com/PyLabRobot/pylabrobot/pull/1378); #1276 and #1342 (CO-RE holder); [#1362 LLD aspirate](https://github.com/PyLabRobot/pylabrobot/pull/1362); [#1333](https://github.com/PyLabRobot/pylabrobot/pull/1333), [#1334](https://github.com/PyLabRobot/pylabrobot/pull/1334), [#1336](https://github.com/PyLabRobot/pylabrobot/pull/1336), [#1352](https://github.com/PyLabRobot/pylabrobot/pull/1352) (probing); [#63](https://github.com/PyLabRobot/pylabrobot/pull/63) (PLACE_SHIFT heights).
- In-repo: `docs/user_guide/hamilton/star/hardware/replacing-iswap.md`; legacy `STARBackend` docstrings (firmware field meanings, "after the firmware guide").
