// A page without a browser, for checking that what a run draws moves smoothly.
//
//   node smoothness_page.mjs <websocket url> '<config json>'
//
// It connects to a viewer as a page does, keeps the scene as positions and parents - no drawing -
// and applies what the server sends the way the page does: `scene`, `state` locations and
// rotations, `moves`, and `motion`, played by the page's own player (`motion_player.js`) with its
// own grip and release (`carry.js`). It steps the player on its own clock, samples where every
// resource is in the world, and reports each step between two samples that is longer than anything
// on the device could have travelled in that time: a jump.
//
// Prints `ready` once it has a scene. When its stdin closes, it writes the report as JSON to the
// config's `report` path and exits. The config: `hz`, samples per second of motion time; `speed`, how much faster than
// the drives to play; `maxSpeed`, the fastest anything may move, in mm/s; `slack`, a factor on
// that; `floor`, a step in mm below which nothing is a jump.

import { writeFileSync } from "node:fs";

import { heldAt, LIDDABLE, MOVABLE, SITES, siteUnder } from "./static/carry.js";
import { createPlayer, turnedLocation } from "./static/motion_player.js";

const [url, configJson] = process.argv.slice(2);
const config = { hz: 20, speed: 4, maxSpeed: 600, slack: 1.5, floor: 1, ...JSON.parse(configJson ?? "{}") };

// -- the scene, as positions and parents -------------------------------------------------------

let names = [];
let models = [];
let modelOf = [];
let parentOf = [];
let childrenOf = [];
let local = new Float64Array(0); // six per resource: x, y, z in mm, then rotation x, y, z in degrees
let indexOfName = new Map();

function buildScene(data) {
  const { instances } = data;
  names = instances.names;
  models = data.models;
  modelOf = instances.model;
  parentOf = [...instances.parent];
  const bytes = Buffer.from(instances.transforms, "base64");
  const floats = new Float32Array(bytes.buffer, bytes.byteOffset, bytes.length / 4);
  local = Float64Array.from(floats);
  indexOfName = new Map(names.map((name, i) => [name, i]));
  childrenOf = names.map(() => []);
  parentOf.forEach((p, i) => {
    if (p >= 0) childrenOf[p].push(i);
  });
}

// 4x4 matrices as 16 numbers, column-major like three's. A resource turns about X, then Y, then Z,
// as the page's `makeRotationFromEuler(..., "XYZ")` turns it.
function localMatrix(i) {
  const o = i * 6;
  const [a, b, c] = [3, 4, 5].map((k) => (local[o + k] * Math.PI) / 180);
  const [ca, sa, cb, sb, cc, sc] = [Math.cos(a), Math.sin(a), Math.cos(b), Math.sin(b), Math.cos(c), Math.sin(c)];
  // three's Euler XYZ: R = Rx * Ry * Rz.
  return [
    cb * cc, ca * sc + sa * sb * cc, sa * sc - ca * sb * cc, 0,
    -cb * sc, ca * cc - sa * sb * sc, sa * cc + ca * sb * sc, 0,
    sb, -sa * cb, ca * cb, 0,
    local[o], local[o + 1], local[o + 2], 1,
  ];
}

function multiply(m, n) {
  const out = new Array(16).fill(0);
  for (let col = 0; col < 4; col++) {
    for (let row = 0; row < 4; row++) {
      let sum = 0;
      for (let k = 0; k < 4; k++) sum += m[k * 4 + row] * n[col * 4 + k];
      out[col * 4 + row] = sum;
    }
  }
  return out;
}

function invertRigid(m) {
  // A rotation and a translation: the inverse is the transposed rotation, and the translation
  // taken back through it.
  const r = [m[0], m[4], m[8], m[1], m[5], m[9], m[2], m[6], m[10]];
  const t = [m[12], m[13], m[14]];
  return [
    r[0], r[3], r[6], 0,
    r[1], r[4], r[7], 0,
    r[2], r[5], r[8], 0,
    -(r[0] * t[0] + r[1] * t[1] + r[2] * t[2]),
    -(r[3] * t[0] + r[4] * t[1] + r[5] * t[2]),
    -(r[6] * t[0] + r[7] * t[1] + r[8] * t[2]),
    1,
  ];
}

// Every resource's world transform, parents first.
function worldMatrices() {
  const out = new Array(names.length);
  const visit = (i) => {
    if (out[i]) return out[i];
    const p = parentOf[i];
    out[i] = p < 0 ? localMatrix(i) : multiply(visit(p), localMatrix(i));
    return out[i];
  };
  for (let i = 0; i < names.length; i++) visit(i);
  return out;
}

const apply = (m, p) => ({
  x: m[0] * p.x + m[4] * p.y + m[8] * p.z + m[12],
  y: m[1] * p.x + m[5] * p.y + m[9] * p.z + m[13],
  z: m[2] * p.x + m[6] * p.y + m[10] * p.z + m[14],
});

function worldBox(i, matrices) {
  const model = models[modelOf[i]];
  const size = [model.size_x || model.diameter || 0.1, model.size_y || model.diameter || 0.1, model.size_z || 0.1];
  const min = { x: Infinity, y: Infinity, z: Infinity };
  const max = { x: -Infinity, y: -Infinity, z: -Infinity };
  for (let c = 0; c < 8; c++) {
    const p = apply(matrices[i], { x: c & 1 ? size[0] : 0, y: c & 2 ? size[1] : 0, z: c & 4 ? size[2] : 0 });
    for (const k of ["x", "y", "z"]) {
      min[k] = Math.min(min[k], p[k]);
      max[k] = Math.max(max[k], p[k]);
    }
  }
  return { min, max };
}

// -- applying what the server sends, as the page does ---------------------------------------------

function setLocal(i, location) {
  local[i * 6] = location.x;
  local[i * 6 + 1] = location.y;
  local[i * 6 + 2] = location.z;
}

function setRotation(i, rotation) {
  local[i * 6 + 3] = rotation?.x ?? 0;
  local[i * 6 + 4] = rotation?.y ?? 0;
  local[i * 6 + 5] = rotation?.z ?? 0;
}

function reparent(i, parent) {
  const was = parentOf[i];
  if (was === parent) return;
  if (was >= 0) childrenOf[was] = childrenOf[was].filter((c) => c !== i);
  if (parent >= 0) childrenOf[parent].push(i);
  parentOf[i] = parent;
}

function applyState(data) {
  for (const [name, slot] of Object.entries(data.of ?? {})) {
    const i = indexOfName.get(name);
    if (i !== undefined) setRotation(i, data.states[slot]?.rotation);
  }
  for (const [name, location] of Object.entries(data.locations ?? {})) {
    const i = indexOfName.get(name);
    if (i !== undefined) setLocal(i, location);
  }
}

function applyMoves(moves) {
  for (const move of moves) {
    const i = indexOfName.get(move.name);
    if (i === undefined) continue;
    reparent(i, move.parent === null ? -1 : (indexOfName.get(move.parent) ?? -1));
    setLocal(i, move.location);
    setRotation(i, move.rotation);
  }
}

// A resource handed to a new holder: where the model will have it, or where it stands. A handover
// that moves what changes hands is reported: it should keep where it is, and only then move.
function reattach(name, parentName, placed) {
  const i = indexOfName.get(name);
  if (i === undefined) return;
  const before = worldMatrices()[i];
  handOver(name, parentName, placed);
  const after = worldMatrices()[i];
  const d = Math.hypot(after[12] - before[12], after[13] - before[13], after[14] - before[14]);
  if (d >= still / 10 && handovers.length < KEEP) {
    handovers.push({
      name,
      category: categoryOf(i),
      mm: round(d),
      t: round(motionTime),
      to: parentName,
      after: lastEvent,
      from: [before[12], before[13], before[14]].map(round),
      landed: [after[12], after[13], after[14]].map(round),
    });
  }
}

function handOver(name, parentName, placed) {
  const i = indexOfName.get(name);
  const parent = parentName === null ? -1 : (indexOfName.get(parentName) ?? -1);
  if (placed && parent >= 0) {
    reparent(i, parent);
    setLocal(i, placed.location);
    setRotation(i, placed.rotation);
    return;
  }
  if (parent === parentOf[i]) return;
  const matrices = worldMatrices();
  const relative = parent >= 0 ? multiply(invertRigid(matrices[parent]), matrices[i]) : matrices[i];
  reparent(i, parent);
  setLocal(i, { x: relative[12], y: relative[13], z: relative[14] });
  // A turn about Z only, which is all a carried thing has here.
  setRotation(i, { x: 0, y: 0, z: (Math.atan2(relative[1], relative[0]) * 180) / Math.PI });
}

const held = new Map();
const categoryOf = (i) => models[modelOf[i]].category;
const candidates = (categories, matrices) =>
  names
    .map((_, index) => index)
    .filter((index) => categories.has(categoryOf(index)))
    .map((index) => ({ index, category: categoryOf(index), box: worldBox(index, matrices) }));

const player = createPlayer({
  readAxis: (i, axis) => local[i * 6 + axis],
  setAxis: (i, axis, value) => {
    local[i * 6 + axis] = value;
  },
  indexOf: (name) => indexOfName.get(name),
  attach: reattach,
  skipping: () => false,
  turnTo: (i, degrees, pivot) => {
    const o = i * 6;
    const here = { x: local[o], y: local[o + 1], z: local[o + 2] };
    setLocal(i, turnedLocation(here, local[o + 5], degrees, pivot));
    local[o + 5] = degrees;
  },
  grip: (gripper, point) => {
    const g = indexOfName.get(gripper);
    if (g === undefined || held.has(gripper)) return;
    const matrices = worldMatrices();
    const taken = heldAt(apply(matrices[g], point), candidates(MOVABLE, matrices));
    if (taken === undefined) return;
    reattach(names[taken], gripper);
    held.set(gripper, names[taken]);
    carried.add(names[taken]);
  },
  release: (gripper) => {
    const name = held.get(gripper);
    held.delete(gripper);
    const i = name === undefined ? undefined : indexOfName.get(name);
    if (i === undefined) return;
    const matrices = worldMatrices();
    const model = models[modelOf[i]];
    const lid = model.category === "lid";
    const seats = candidates(lid ? new Set([...SITES, ...LIDDABLE]) : SITES, matrices).map((c) =>
      LIDDABLE.has(c.category)
        ? { ...c, covered: childrenOf[c.index].some((k) => k !== i && categoryOf(k) === "lid") }
        : c,
    );
    const site = siteUnder(worldBox(i, matrices), seats, {
      index: i,
      category: model.category,
      nesting: model.nesting_z_height,
    });
    reattach(name, site === undefined ? null : names[site]);
  },
});
player.setSpeed(config.speed);

// -- the clock, the samples, and what moved -----------------------------------------------------
//
// Three things are reported. A jump: a step between two samples longer than anything could travel
// in that time. A stray: something moving during a motion that the motion does not move - nothing
// it names, and nothing standing on what it names. A snap: anything moving outside a motion at all,
// which is the model putting something somewhere without a motion to draw the way there - a
// command the viewer does not act out, or a motion that ended somewhere else than the model did.

const FRAME_S = 1 / 60;
const sampleEvery = 1 / config.hz; // in the drives' time
// mm: less than this is not a move. State travels rounded to a tenth - a tenth of a degree is a
// third of a mm at the end of the iSWAP's arm - so a scene and the first state after it disagree by
// that much without anything having moved.
const still = config.still ?? 0.5;
// How many of each kind of finding are kept: the first ones are what explain the rest.
const KEEP = 500;
let motionTime = 0; // how much of the drives' time has been played
let lastSampleAt = 0;
let last = null; // positions at the previous sample
let lastEvent = "scene";
// The motions under way, by id, with the names each moves. The device runs some at once - an X-arm
// move beside a Y move of the channels - so a thing moved by any of them is expected to move.
const active = new Map();
const jumps = [];
const strays = [];
const snaps = [];
// Tips, plates and lids that moved in being handed over, rather than keeping where they were.
const handovers = [];
// A model update that finds the page somewhere else than it says: the motion ended short, long or
// beside where the model has the resource.
const arrivals = [];
// Commands the viewer does not act out, as they went by.
const undecoded = new Set();
// What the page moved on its own - labware taken by a gripper - and so is expected to differ from
// the model, which never moves it.
const carried = new Set();
// How far a model update may disagree with the page, in mm and degrees: state travels rounded to a
// tenth, and a motion's targets to a hundredth.
const ARRIVAL_MM = config.arrivalMm ?? 0.11;
const ARRIVAL_DEG = config.arrivalDeg ?? 0.11;
let samples = 0;
let motions = 0;

// Whether a resource is moved by a motion under way: it or something under which it stands is
// named. Asked of the tree as it is now, so a plate taken onto a gripper is moved with the gripper.
function movedByMotion(i) {
  for (let at = i; at >= 0; at = parentOf[at]) {
    for (const names_ of active.values()) if (names_.has(names[at])) return true;
  }
  return false;
}

function namedIn(request) {
  const found = new Set();
  if (request.arm) found.add(request.arm.name);
  for (const key of ["channels", "traverse", "moves", "turns", "attach"]) {
    for (const entry of request[key] ?? []) found.add(entry.name);
  }
  if (request.jaws) {
    found.add(request.jaws.gripper);
    for (const finger of request.jaws.fingers) found.add(finger.name);
  }
  // A tip handed to a spot moves under the spot's name at the end, and what a gripper holds rides
  // with it: both are covered by what they stand under once they are there.
  return found;
}

const round = (v) => Math.round(v * 100) / 100;

function sample() {
  const dt = Math.max(motionTime - lastSampleAt, 1e-9);
  lastSampleAt = motionTime;
  const matrices = worldMatrices();
  const now = matrices.map((m) => [m[12], m[13], m[14]]);
  if (last && last.length === now.length) {
    const allowed = config.maxSpeed * dt * config.slack + config.floor;
    for (let i = 0; i < now.length; i++) {
      const d = Math.hypot(now[i][0] - last[i][0], now[i][1] - last[i][1], now[i][2] - last[i][2]);
      if (d < still) continue;
      const seen = {
        name: names[i],
        category: categoryOf(i),
        mm: round(d),
        t: round(motionTime),
        after: lastEvent,
        from: last[i].map(round),
        to: now[i].map(round),
      };
      if (d > allowed && jumps.length < KEEP) jumps.push({ ...seen, allowed: round(allowed) });
      if (active.size === 0) {
        if (snaps.length < KEEP) snaps.push(seen);
      } else if (!movedByMotion(i) && strays.length < KEEP) {
        strays.push(seen);
      }
    }
  }
  last = now;
  samples++;
}

setInterval(() => {
  if (!names.length) return;
  player.step(FRAME_S);
  // The player runs `speed` times as fast as the drives, so a frame is that much of their time.
  motionTime += FRAME_S * config.speed;
  if (motionTime - lastSampleAt >= sampleEvery) sample();
}, FRAME_S * 1000);

// -- the connection -----------------------------------------------------------------------------

const angleOff = (a, b) => Math.abs(((((a - b) % 360) + 540) % 360) - 180);

// Where a model update puts things, against where the page already has them.
function checkArrivals(kind, data) {
  if (!names.length) return;
  const entries =
    kind === "moves"
      ? data.moves
      : Object.keys(data.of ?? {})
          .map((name) => ({ name, rotation: data.states[data.of[name]]?.rotation ?? { x: 0, y: 0, z: 0 } }))
          .concat(Object.entries(data.locations ?? {}).map(([name, location]) => ({ name, location })));
  for (const entry of entries) {
    const i = indexOfName.get(entry.name);
    if (i === undefined || carried.has(entry.name)) continue;
    const o = i * 6;
    const found = { name: entry.name, category: categoryOf(i), t: round(motionTime), kind, after: lastEvent };
    if (entry.location) {
      const d = Math.hypot(local[o] - entry.location.x, local[o + 1] - entry.location.y, local[o + 2] - entry.location.z);
      if (d > ARRIVAL_MM && arrivals.length < KEEP) {
        arrivals.push({ ...found, mm: round(d), page: [...local.slice(o, o + 3)].map(round), model: [entry.location.x, entry.location.y, entry.location.z].map(round) });
      }
    }
    if (entry.rotation) {
      const off = Math.max(...["x", "y", "z"].map((k, j) => angleOff(local[o + 3 + j], entry.rotation[k] ?? 0)));
      if (off > ARRIVAL_DEG && arrivals.length < KEEP) {
        arrivals.push({ ...found, degrees: round(off), page: [...local.slice(o + 3, o + 6)].map(round), model: ["x", "y", "z"].map((k) => round(entry.rotation[k] ?? 0)) });
      }
    }
  }
}

// `trace`: a resource name whose every change is written to stderr, to find where a jump comes from.
function trace(kind, detail) {
  if (!config.trace) return;
  const i = indexOfName.get(config.trace);
  const at = i === undefined ? null : [...local.slice(i * 6, i * 6 + 3)].map(round);
  process.stderr.write(
    `${motionTime.toFixed(3)} ${kind} ${JSON.stringify(detail)} -> local ${JSON.stringify(at)}\n`,
  );
}

const socket = new WebSocket(url);
socket.onopen = () => socket.send(JSON.stringify({ event: "hello", data: { backend: "headless" } }));
socket.onmessage = async (message) => {
  const { event: kind, data } = JSON.parse(String(message.data));
  if (kind === "scene") {
    const first = !names.length;
    buildScene(data);
    held.clear();
    last = null; // a new scene is not a move
    lastEvent = "scene";
    if (first) process.stdout.write("ready\n");
    return;
  }
  if (kind === "command") {
    undecoded.add(data.command);
    lastEvent = `command ${data.command} (not acted out)`;
    return;
  }
  if (kind === "state" || kind === "moves") {
    checkArrivals(kind, data);
    // Sampled on either side, so whatever it moves is put down to it.
    if (names.length) sample();
    if (config.trace) {
      const mine = kind === "state" ? data.locations?.[config.trace] : data.moves.find((m) => m.name === config.trace);
      if (mine) trace(`${kind}-before`, mine);
    }
    lastEvent = kind;
    if (kind === "state") applyState(data);
    else applyMoves(data.moves);
    trace(`${kind}-after`, null);
    sample();
    return;
  }
  if (kind === "motion") {
    motions++;
    sample();
    lastEvent = `motion ${data.command}`;
    trace("motion-before", data.command);
    active.set(data.id, namedIn(data));
    await player.play(data);
    sample();
    active.delete(data.id);
    trace("motion-after", data.command);
    lastEvent = `after ${data.command}`;
    socket.send(JSON.stringify({ event: "motion_done", data: { id: data.id } }));
  }
};

process.stdin.resume();
process.stdin.on("end", () => {
  sample();
  const matrices = names.length ? worldMatrices() : [];
  const final = Object.fromEntries(names.map((name, i) => [name, [matrices[i][12], matrices[i][13], matrices[i][14]].map(round)]));
  writeFileSync(
    config.report,
    JSON.stringify({
      samples,
      motions,
      motionTime,
      jumps,
      strays,
      snaps,
      handovers,
      arrivals,
      undecoded: [...undecoded].sort(),
      carried: [...carried],
      final,
    }),
  );
  process.exit(0);
});
