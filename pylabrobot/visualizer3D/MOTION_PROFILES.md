# Motion profiles, by firmware command

What the viewer plays for each Hamilton STAR firmware command, and where every number and choice
comes from. Each command the v1 driver sends either has a motion profile (made of phases, played in
order) or has none. Each value is tagged with its source:

| Tag | Meaning |
|---|---|
| **FW** | Carried by the command itself: the page plays what the device was told. |
| **PLR** | A value or model in PyLabRobot's code: a driver constant, a configuration, or the resource model. Cited by file and symbol. |
| **SIM** | How PLR's STAR simulator records the command (`hamilton/star/driver/simulator.py`). This is PLR's own model of the motion, not a documented firmware sequence. |
| **DOC** | External documentation or a forum post, linked to the post. labautomation.io posts by Hamilton staff are treated as authoritative. |
| **HEUR** | Our choice, with no documented reference. The justification is given. |

Files: the decoder is `pylabrobot/visualizer3D/motion.py` (Python, turns a command into targets);
the player is `static/motion_player.js` (the page, plays targets in phases); the profile is
`static/motion_profile.js`.

---

## 0. Applies to every profile

| Choice | Value | Tag | Source / justification |
|---|---|---|---|
| Speed profile of a single move | Symmetric trapezoid: accelerate, cruise, decelerate; a triangle if too short to reach cruise; constant speed when no acceleration is known | SIM | Same timing model as the simulator: `SimulatedPipettes._get_travel_time` (`simulator.py`) takes d/v + v/a, or 2√(d/a) as a triangle. Page: `motionProfile` in `static/motion_profile.js` (it also came from threejs_visualizer's `calculateMotionProfile`). The real drives' ramp shape (e.g. S-curve jerk limits) is not public. |
| Moves that happen at once | Drives in the same phase start together, and the phase ends with the slowest | SIM | `owe_motion_time`: "the drives move at once, so a command takes as long as its slowest axis" (`simulator.py`). |
| Smallest move played | 0.05 mm (`STILL`); anything smaller is skipped | HEUR | Below the 0.1 mm firmware resolution; avoids zero-length tweens. |
| Model arrivals | After each motion, the model's own update must find the page already there (0.11 mm / 0.11° tolerance in the harness) | PLR + HEUR | The model is the source of truth (PLR). The tolerance is ours: `ARRIVAL_MM` / `ARRIVAL_DEG` in `smoothness_page.mjs`, just above the firmware's 0.1 mm resolution. Enforced by `smoothness.py`'s `assert_smooth`. |
| Page hidden / background tab | Motions jump to their end | HEUR | Browsers throttle hidden tabs, and blocking the run on an unwatched page makes no sense. |
| Python waits for the page | Until every connected page reports `motion_done`, at most 120 s (`Viewer3D.MOTION_TIMEOUT_S`) | HEUR | Paces the simulated run to the drawing; the timeout keeps a stuck page from hanging a run. |
| Heights | Converted to where the channel's stop disc is; the lowest point of a mounted tip is the disc minus the tip's overhang | PLR + SIM | `_Frames.lowest_point_z`, with the overhang from `SimulatedPipettes._below_stop_disc`. The master reports the lowest point of what a channel carries (`simulator.py` `RZ`). For CO-RE grip tools this is the grip line (`HamiltonCoreGripperTool.grip_line_height`). **Gap:** `_below_stop_disc` exists only on the simulator. Driving a real STAR, the decoder takes the overhang as 0, so heights with a tip mounted would be off by the tip's length. It should come from the model (`TipMountingShaft.tip_bottom`) instead. |

### Drive speeds used when the command does not state one

| Drive | Speed | Acceleration | Tag | Source |
|---|---|---|---|---|
| X-arm | 400 mm/s | 500 mm/s² | HEUR | The v1 driver states neither. These are threejs_visualizer's values (`X_SPEED`, `X_ACCELERATION`, `motion.py`). Firmware X commands carry only an acceleration *level*. |
| Channel Y | 250 mm/s | none (constant speed) | PLR + HEUR | Speed: `Pipettes.default_y_speed`. The firmware states Y acceleration only as a level (1–4, `default_y_acceleration_level = 3`), not a rate, and the simulator times Y at constant speed, so the page does too. |
| Channel Z | 125 mm/s | 800 mm/s² | PLR | `Pipettes.default_z_speed`, `Pipettes.default_z_acceleration`. |
| 96-head Y / Z | the head's defaults | the head's defaults | PLR | `HeadConfiguration.y_drive_speed_default` / `z_drive_speed_default` and their accelerations (`features/head.py`): the value the firmware reports when read, else the configured default increments. |
| iSWAP gripper, when a close states no speed | `gripper_close_speed_default_increments` (5000), converted | `gripper_acceleration_default_increments` (75), converted | PLR | `iSWAPConfiguration` (`features/iswap.py`). |

---

## 1. Channel commands

### `C0 TP` — tip pick-up (`Pipettes.pick_up_tips`)
Profile: **stroke with handover**.

| Phase | Target | Tag | Source |
|---|---|---|---|
| 1. Rise | Any channel lower than `th` rises to it (by lowest point) | FW + SIM | `th`. The simulator records the stroke "across at the height it starts from" (`_record_tip_command`). |
| 2. Across | The arm to the X of the last column (`xp`); the channels to `yp`; the channels not named pushed along the rail by the spacing rule | FW + PLR + SIM | Positions are FW. Pushing the others follows `Pipettes._plan_y_positions(make_space=True)`, as the simulator does ("one rail", `_record_tip_command`). Ported as `_Frames.planned_ys`. |
| 3. Down | The lowest point to `tz` | FW | `tz`. |
| 4. Handover | Each spot's tip goes to the channel's shaft, placed as `TipMountingShaft.mount_tip` places it, then seated at the Z drive's pace | PLR + HEUR | The placement is PLR (`_mounted_location`). Seating the tip at the Z-drive pace instead of snapping it is ours (HEUR): the model's placement and the stroke's bottom differ by the fitting geometry. |
| 5. Up | The lowest point to `th`, now with the tip's overhang | FW + PLR | The overhang is the tip type's defined length (`STARDriver.defined_tip_lengths`). |

Also used: begin height `tp` = spot + collar height (PLR, legacy `STARBackend.pick_up_tips`, per `_pick_up_tips_in_one_move`).

### `C0 TR` — tip drop / return (`drop_tips`, `return_tips`, `discard_tips`)
Profile: **stroke with handover**.

| Phase | Target | Tag | Source |
|---|---|---|---|
| 1–2 | As `C0 TP` | FW + SIM | |
| 3. Down | `tz`. With `ti=1` (DROP) this is the stop disc's height; with PLACE_SHIFT it is where the tip's cone ends | PLR | `_unchecked_fw_drop_tips` docstring: "With `PLACE_SHIFT` the heights are where the tip's cone ends; with `DROP`, the stop disc's." |
| 4. Handover | The tip goes to the spot under the channel (placed by `resting_location`), or nowhere (waste) | PLR | `tip_rack.resting_location`. |
| 5. Up | To `te`, empty | FW | |

Default heights: DROP begins at spot + collar and ends a fitting depth lower; PLACE_SHIFT uses 59.9 / 49.9 mm (PLR, legacy "Empirical, from legacy: https://github.com/PyLabRobot/pylabrobot/pull/63").

### `C0 AS` — aspirate (`Pipettes.aspirate`)
Profile: **stroke with dwell and leave**.

| Phase | Target | Tag | Source |
|---|---|---|---|
| 1–2 | As `C0 TP` | FW + SIM | |
| 3. Down | max(`zl` − `ip`, `zx`): the surface less the immersion depth, no lower than the minimum height | FW | Field meanings are in legacy's `STARBackend.aspirate_pip` docstring (after the firmware guide): `zl` "Liquid surface at function without LLD", `ip` "Immersion depth", `zx` "Minimum height (maximum immersion depth)". |
| 4. Dwell | Longest channel of (`av` / `as`) + `wt` | FW | Volume ÷ flow rate, plus the settling time. |
| 5. Leave | Up to the surface at the swap speed `de` | FW | `de` "Swap speed (on leaving liquid)" (legacy docstring; default 10 mm/s). |
| 6. Up | To `te` | FW | |

Known divergences from the device (to do):
- **Surface following is not played.** The tip should descend by `fp` over the dwell. `fp` is "the total distance the tip moves during aspiration, from the surface down to the new, reduced height" (PLR maintainer, [discuss.pylabrobot.org/t/304/6](https://discuss.pylabrobot.org/t/hamilton-surface-following-issues/304/6)).
- `it` (immersion direction: 0 deeper, 1 up out of the liquid) is ignored.
- `po` (transport-air pull-out, 5 mm without LLD) is not played.
- The conical second section (`zu`, `zr`) is not played.
- In v1, LLD is **never** done inside `C0AS`: capacitive/pressure searches run first as their own commands (see `Px ZL` / `Px ZE`, section 5), and `C0AS` goes with LLD off (PR [#1362](https://github.com/PyLabRobot/pylabrobot/pull/1362)). So `C0AS` itself needs no search phase.

### `C0 JY` — channels to Y positions
Profile: **single axis (Y)**. Each channel to `yp` (FW), at the Y drive speed (section 0).

### `C0 JZ` — channels to Z positions
Profile: **single axis (Z)**. Each channel's lowest point to `zp` (FW), at the Z drive speed and acceleration (section 0).

### `C0 FY` — free the Y range (the iSWAP's `make_space`)
Profile: **single axis (Y), targets written first**. The master packs the channels as far forward as they fit, each against the one in front. The target isn't in the command: the simulator writes it before the command is sent (`recorded_first`), and the page plays to it (SIM).

### `C0 ZA` — all channels to Z safety
Profile: **single axis (Z), targets written first**. Every channel up to the top of its Z travel, `Pipettes.configuration.z_range[1]`, where `probe_z_max` leaves them (PLR). The target comes from the simulator (`recorded_first`, SIM).

### `C0 ZT` — pick up the CO-RE grip tools (`Pipettes.pick_up_core_gripper_tools`)
Profile: **stroke with handover**, on two adjacent channels.

| Phase | Target | Tag | Source |
|---|---|---|---|
| 1–2 | Both channels to the tools' pick-up points: X `xs`, Y `ya` (back) / `yb` (front) | FW + PLR | Points come from the model: each tool's `pick_up_location` (`resources/hamilton/core_gripper_tools.py`), in the holder at `channel_x_center` and its front/back channel Y centres (`core_grippers.py`). They match legacy's wire exactly (`xs07975 ya1250 yb1070` on a STARlet, legacy `STAR_tests.py`). |
| 3. Down | `tz` = tool top − 10 mm, by the stop disc (the channel is bare) | PLR + HEUR | Heights are legacy's (`pick_up_core_gripper_tools`: begin 235, end 225, against tools whose tops stand at 235.0, probed per `hamilton_core_gripper_1000ul_5ml_on_waste`). Reading `tz` as a stop-disc height is ours (HEUR): the firmware's reference point for `ZT` heights is not documented publicly. |
| 4. Handover | Each tool onto its shaft, placed by `mount_tip` (pick-up location on the shaft's axis) | PLR | `TipMountingShaft.mount_tip`. |
| 5. Up | `th`, with the tool hanging by its grip line (pick-up z − fitting depth − grip-line height) | PLR + SIM | Matches what the simulator reports for a channel carrying a tool. |

Travel height `th`: as high as a tool on a channel reaches (v1's convention for tip commands, `_tip_traverse_height`). Legacy sends the iSWAP traversal height, 280 mm (PLR, `_iswap_traversal_height`); `minimum_traverse_height=280` reproduces it.

### `C0 ZS` — return the CO-RE grip tools (`return_core_gripper_tools`)
Profile: **stroke with handover**, the reverse of `C0 ZT`. The channels go to where the tools were parked (remembered at pick-up). Down to `tz` = tool top − 30 mm (legacy: begin 215, end 205; PLR). Here `tz` is read as the lowest point *with* the tool mounted (HEUR, as for `ZT`). Each tool goes back to its parked location and rotation (PLR), then the channels rise to `te`.

---

## 2. X-arm

### `X0 XP` / `X0 SP` — arm to an X position
Profile: **single axis (X)**. `XP` is the left arm and `SP` the right. The target is the arm's `…a` field, in increments converted by `XArmConfiguration.x_increments_to_mm`, less `reference_point_from_left` (FW + PLR), at 400 mm/s and 500 mm/s² (HEUR, section 0). Everything on the arm (channels, 96-head, iSWAP) rides with it (PLR: they're children of the arm resource).

---

## 3. iSWAP

Joint conventions (DOC, Camillo Moschner, [discuss.pylabrobot.org/t/517/1](https://discuss.pylabrobot.org/t/intro-to-epic-tame-the-iswap/517/1)):
- Rotation (elbow) −90° / 0° / +90° = left / front / right.
- Wrist −135° / −45° / +45° / +135° = right / straight / left / reverse.

In PLR these are `iSWAPConfiguration`'s predefined increments, read at setup.

### `R0 YA` / `R0 ZA` — the head along Y / Z
Profile: **single axis**.
- Y: to `ya` at `yv`, converted by the arm's configuration (FW + PLR). No acceleration rate, since `R0 YA` carries only a level, so it plays at constant speed (HEUR, as channel Y).
- Z: to `za` + `elbow_z_offset_above_finger` at `zv`, with acceleration `zr` × 1000 increments/s² (FW + PLR).

### `R0 PA` — elbow and wrist together
Profile: **two joint turns, together**. Each joint to its own angle at its own speed and acceleration (`wa`/`wv`/`wr` for the elbow, `ta`/`tv`/`tr` for the wrist; FW), converted by `iSWAPConfiguration` (PLR). Each turns about the pivot the driver turns it about (`proximal_joint`; PLR). Both run on a straight line in joint space (HEUR; the controller's interpolation is not public).

### `R0 GA` — jaws to a width
Profile: **jaws**. The fingers move to the width `ga` at `gv` / `gr` (FW). Each finger travels half the width change in the same time, so at half the drive's speed (derived from symmetric jaws). If opening, the page lets go of what it held *before* moving; if closing, it takes hold *after* (HEUR: the ordering that avoids dragging or dropping the plate mid-motion).

### `C0 GC` — close onto an object
Profile: **jaws**. Closes to `gb` at the default close speed and acceleration (PLR, section 0), then takes hold (HEUR, as `R0 GA`).

### Plate and lid moves (`iSWAPTransport`, Python, from the primitives above)
The compound commands (`C0 PP` / `PR` / `PM`) are not used. Their internal motion isn't public, and the firmware "choos[es] among multiple valid poses unpredictably" (DOC, [discuss.pylabrobot.org/t/517/1](https://discuss.pylabrobot.org/t/intro-to-epic-tame-the-iswap/517/1)). A move is planned as primitives (`hamilton/star/driver/features/iswap_transport.py`):

| Choice | Value | Tag | Source / justification |
|---|---|---|---|
| Phases | open → rise → travel → descend → grip / release → rise | HEUR | Follows the phases `C0 PP`'s parameters describe (open width, traverse height, grip height, end height). |
| Travel height | `iswap.default_minimum_traverse_height` (284 mm), fixed, never computed from the deck | PLR | Legacy sends 280 mm. |
| Grip width, open margin, strength, tolerance, pick-up depth | width across the plate; +3 mm; 4; 2 mm; 5 mm below the top (or `preferred_pickup_location`) | PLR | Legacy `STARBackend.pick_up_resource`. |
| Grip below a lid | 2 mm below the lid's skirt (`nesting_z_height`) | HEUR | Jaws closing within the skirt would close on the lid. |
| Elbow configuration | Only the three elbow stops; the stop with the smallest joint turn from now, front on ties | HEUR | The stops are PLR/DOC; the ranking is ours. |
| Travel order | Y then turn, else turn then Y, else turn at a safe Y = max(y_min, min(now, target, y_max − link 1 − tool)) | HEUR | Chosen so the turn never sweeps the arm behind the rail. Checked by sampling each turn at 36 points against `_check_pose_reachable`. |
| X during travel | Runs concurrently with Y and the turn | HEUR | The X-arm is a separate drive. |

### Not decoded
- `C0 PG` park: close the jaws, lift to the traverse height, retract ("Sending no height leaves that to the master, which does not raise the arm"; PLR, `iSWAP.park` docstring). A rotation-drive calibration lists a parking position of ≈29500 increments (≈+91°) (DOC, [discuss.pylabrobot.org/t/517/4](https://discuss.pylabrobot.org/t/intro-to-epic-tame-the-iswap/517/4)). The retract path itself is not public.
- `R0 GB` close to an object, `R0 GS` relative jaw move: jaws profiles, not yet mapped.
- `C0 FI`, `R0 GI`: initialisation; no public profile.
- Venus 6.2 teaches custom Get/Place paths as waypoint poses (Transport Paths Editor), documented only in the non-public Venus 6.2 Programmer's Manual (DOC, [labautomation.io/t/5759](https://labautomation.io/t/transport-paths-editor/5759)).

---

## 4. 96-head

### `C0 EP` / `C0 ER` — tip pick-up / drop
Profile: **stroke with handover**, all 96 shafts. The head goes to `xs` (sign from `xd`) and `yh`, down and up as the tip commands (FW). Channel A1 goes to spot A1 (PLR: `Head96` / `NChannelPipette` layout). The head's drive defaults are in section 0. The simulator places the head after the command (`SimulatedHead96._place_after_tip_command`: arm X, head Y, z = ze + overhang; SIM).

### `H0 YA` / `H0 ZA` — the head along Y / Z
Profile: **single axis**, to the target at `yv`/`yr` or `zv`/`zr` (FW), converted by `HeadConfiguration` (PLR).

### Not decoded
- `H0 PA` / `H0 PB` aspirate / dispense (a stroke with dwell, like `C0 AS`).
- `C0 EM` move to a coordinate.
- `H0 ZL` cLLD probe (see section 5).
- `H0 DQ` dispensing drive (piston only, no visible motion).
- Touch-off is not available on the multi-probe head: "the MPH is a significantly heavier tool … making this feature impractical" (DOC, Hamilton, [labautomation.io/t/1788/2](https://labautomation.io/t/touch-off-with-mph/1788/2)).

---

## 5. Not decoded yet, with what is known

### Detection searches — `Px ZL` (cLLD), `Px ZE` (pLLD), `Px ZH` (Z-touch), `C0 XL`, `Px YL`
Profile to build: **search**. Each channel on its own, all concurrently:
1. approach to the start;
2. a slow constant-speed descent (or traverse, for X/Y) at the search speed, until detection or the end;
3. a small post-detection move;
4. then stay, or go to Z safety.

Channels stop at different heights at different moments.

| Parameter | Firmware field | Tag | Source |
|---|---|---|---|
| Start, end (stop-disc heights) | `zc`, `zh` (ZL/ZE); `zb`, `za` (ZH) | FW | `_unchecked_fw_probe_z_using_clld` / `_plld` / `_ztouch` docstrings (`pipettes.py`). |
| Search speed, acceleration | `zl`, `zr` (ZL); `zu`, `zr` (ZH); approach `zv` (ZH) | FW | Same. |
| After detection | `zj` (0 down, 1 up) by `zi` | FW | Same. |
| Z-touch force | detection limiter PWM `cg`, push-down PWM `cf` | FW | Same. Touch-off "relies on force feedback to determine when the channel is contacting the bottom surface" (DOC, Hamilton, [labautomation.io/t/1788/2](https://labautomation.io/t/touch-off-with-mph/1788/2)). Needs channel firmware from March 2022 on (DOC, [discuss.pylabrobot.org/t/543/3](https://discuss.pylabrobot.org/t/reason-behind-z-touch-only-being-available-to-8-channels-made-in-2022-and-onwards/543/3)). |
| Where searches start and stop | 5 mm above a container's top (2 mm for wells); 1 mm below the modelled cavity bottom | PLR | `Pipettes.search_start_clearance`, `well_search_start_clearance`, `search_limit_below_cavity_bottom`. |
| Sequence in an LLD aspirate | `Px DC` (blow-out air, in air) → approach → searches → `C0 RL` → `C0 AS` with LLD off | PLR | PR [#1362](https://github.com/PyLabRobot/pylabrobot/pull/1362). |
| **Where it stops** | not in the command; known only from the answer (`C0 RL`, or the model the simulator moves) | — | Needs post-answer targets: play the descent to where the model reports (exact in the simulator), or an open-ended descent at search speed that stops when the answer lands (on hardware). |

### Single-channel and arm moves
- `Px ZA`: one channel to a stop-disc Z. A single-axis Z move (FW).
- `C0 JE`: "the device spreads them itself, over the same band the initialization procedure uses" (PLR, `spread_channels`). The targets are the band spread evenly (PLR, `default_initialize_y_positions`).
- `C0 JP`: frees one channel as much as possible; "the device decides where the others go" (PLR, `make_max_space_for_channel`). Targets are known only after the answer.
- `C0 KX` / `KR`: "The master raises what the arm carries before it travels" to Z safety, then X (PLR, `_unchecked_fw_move_x_with_attached_components_at_z_safety`). Profile: Z-safety phase, then X.
- `Px DC`: blow-out air drawn in air. Piston only, no visible motion.

### Side touch (dispense; v1 has no dispense yet)
"The channel will go down to the touch-off z-height specified, then moves over to the right, dispense, and then moves up" (DOC, Hamilton, [labautomation.io/t/2255/6](https://labautomation.io/t/post-dispense-tip-touch-on-starlet/2255/6)). "It is restricted to a positive x-movement so to the right. Max distance is 4.5mm" (DOC, Hamilton, [labautomation.io/t/2255/9](https://labautomation.io/t/post-dispense-tip-touch-on-starlet/2255/9)). Legacy's `C0 DS` carries a side-touch distance.

### Autoload, initialisation
- Autoload (`I0 YA/ZA/YP/ZP`, `C0 IV`, the barcode scanner move, carrier load/unload): no public profile. Loading moves a carrier into the tree.
- Initialisation (`C0 DI`, `C0 FI`, `X0 XI`, the heads): no public profile.

---

## 6. Commands with no motion profile
Reads (`R*`, `Q*`, `VW`), pressure-monitoring and sensor setup (`AC`, `AF`, `AN`, `AQ`, `BG`, `BH`), drive parameters (`AA`), brakes (`R0 BA/BO`), drive power (`X0 XO`, `R0 GO`), cover (`C0 CO/HO/CE/CD`), tip-type definition (`C0 TT`), master setup (`C0 UA`, `C0 VI`), and autoload sensing and barcode setup (`CQ`, `CS`, `CT`, `CB`, `CP`, `AR`, `AF`).

---

## 7. Liquid, as drawn (not a firmware command)
A vessel's cavity is tinted from white to orange by volume ÷ capacity, stepping to 35% for any liquid at all (PR #1378 page, `live.js` `refreshOverlays`; not ours). It changes when the model's state update arrives, after the command. Tips show their contents only in the 2D channel panel. Moving liquid (a surface lowered over the dwell, a column rising in the tip) is not drawn yet. The data for it are PLR's (`Container.compute_height_from_volume`) plus the `C0 AS` fields above.

---

## Sources
- PyLabRobot forum: [surface following, post 6](https://discuss.pylabrobot.org/t/hamilton-surface-following-issues/304/6); [z-touch firmware, posts 2–3](https://discuss.pylabrobot.org/t/reason-behind-z-touch-only-being-available-to-8-channels-made-in-2022-and-onwards/543/3); [Tame the iSWAP, post 1](https://discuss.pylabrobot.org/t/intro-to-epic-tame-the-iswap/517/1) and [post 4](https://discuss.pylabrobot.org/t/intro-to-epic-tame-the-iswap/517/4).
- labautomation.io: [side touch, post 6](https://labautomation.io/t/post-dispense-tip-touch-on-starlet/2255/6) and [post 9](https://labautomation.io/t/post-dispense-tip-touch-on-starlet/2255/9); [touch-off and the MPH, post 2](https://labautomation.io/t/touch-off-with-mph/1788/2); [Transport Paths Editor](https://labautomation.io/t/transport-paths-editor/5759).
- PyLabRobot PRs: [#1362 LLD aspirate](https://github.com/PyLabRobot/pylabrobot/pull/1362), [#1333 cLLD](https://github.com/PyLabRobot/pylabrobot/pull/1333), [#1334 pLLD](https://github.com/PyLabRobot/pylabrobot/pull/1334), [#1336 probing](https://github.com/PyLabRobot/pylabrobot/pull/1336), [#1352 96-head cLLD](https://github.com/PyLabRobot/pylabrobot/pull/1352), [#63 PLACE_SHIFT heights](https://github.com/PyLabRobot/pylabrobot/pull/63).
