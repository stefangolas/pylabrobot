// The motion player, outside a page: `node --test pylabrobot/visualizer3D/motion_player_tests.mjs`.
// Run from Python by `motion_tests.py`, which skips it where there is no Node.

import assert from "node:assert/strict";
import { test } from "node:test";

import { createPlayer } from "./static/motion_player.js";
import { motionProfile } from "./static/motion_profile.js";

const DRIVES = {
  x: { speed: 400, acceleration: 500 },
  y: { speed: 250, acceleration: null },
  z: { speed: 125, acceleration: 800 },
};

// A world of named resources with positions, recording every change in order.
function fakeWorld(positions) {
  const names = Object.keys(positions);
  const at = names.map((n) => [...positions[n]]);
  const log = [];
  const parents = {};
  return {
    log,
    parents,
    at: (name) => at[names.indexOf(name)],
    deps: (skipping = () => false) => ({
      readAxis: (i, axis) => at[i][axis],
      setAxis: (i, axis, value) => {
        at[i][axis] = value;
        log.push({ name: names[i], axis, value });
      },
      indexOf: (name) => (names.includes(name) ? names.indexOf(name) : undefined),
      attach: (name, parent) => {
        parents[name] = parent;
        log.push({ attach: name, parent, z: at[names.indexOf("ch0")][2] });
      },
      skipping,
    }),
  };
}

// Play to the end in fixed frames, as the frame loop would, and say how long it took.
async function playOut(player, request, frame = 1 / 60) {
  let done = false;
  const playing = player.play(request).then(() => {
    done = true;
  });
  let seconds = 0;
  for (let i = 0; i < 100000 && !done; i++) {
    await new Promise((resolve) => setImmediate(resolve)); // let finished moves start the next
    if (done) break;
    player.step(frame);
    seconds += frame;
  }
  await playing;
  return seconds;
}

const pickUp = {
  kind: "tip_pickup",
  arm: { name: "arm", x: 300 },
  traverse: [{ name: "ch0", z: 0 }],
  channels: [{ name: "ch0", channel: 0, y: 200, down: -100, end: 10 }],
  attach: [{ name: "tip", parent: "shaft0" }],
  dwell: 0,
  drives: DRIVES,
};

const start = () => ({ arm: [100, 0, 0], ch0: [0, 150, 10], tip: [0, 0, 0] });

test("a pick-up goes across, then down, takes the tip at the bottom, then comes up", async () => {
  const world = fakeWorld(start());
  await playOut(createPlayer(world.deps()), pickUp);

  const firstZ = world.log.findIndex((e) => e.axis === 2);
  const across = world.log.slice(0, firstZ);
  assert.ok(across.some((e) => e.name === "arm") && across.some((e) => e.axis === 1));
  // The arm and the channel travel together: their changes interleave rather than follow.
  const lastArm = across.findLastIndex((e) => e.name === "arm");
  const firstY = across.findIndex((e) => e.axis === 1);
  assert.ok(firstY < lastArm, "the channel waited for the arm");

  const handover = world.log.findIndex((e) => e.attach === "tip");
  assert.ok(handover > firstZ, "the tip was taken before the channel went down");
  assert.equal(world.log[handover].z, -100, "the tip was taken away from the bottom");
  assert.equal(world.parents.tip, "shaft0");
  const after = world.log.slice(handover + 1).filter((e) => e.axis === 2);
  assert.ok(after.length > 1 && after.at(-1).value === 10, "the channel did not come back up");
  assert.deepEqual(world.at("arm"), [300, 0, 0]);
  assert.deepEqual(world.at("ch0"), [0, 200, 10]);
});

test("a move passes through the positions between, forward only", async () => {
  const world = fakeWorld(start());
  await playOut(createPlayer(world.deps()), pickUp);
  const xs = world.log.filter((e) => e.name === "arm").map((e) => e.value);
  assert.ok(xs.filter((x) => x > 101 && x < 299).length >= 10, "the arm jumped");
  for (let i = 1; i < xs.length; i++) assert.ok(xs[i] >= xs[i - 1], "the arm went backwards");
});

test("a motion takes as long as its drives say", async () => {
  const world = fakeWorld(start());
  const seconds = await playOut(createPlayer(world.deps()), pickUp);
  // Across is the slower of X and Y; then down and back up in Z.
  const across = Math.max(
    motionProfile(200, 400, 500).duration,
    motionProfile(50, 250, null).duration,
  );
  const expected =
    across + motionProfile(110, 125, 800).duration + motionProfile(110, 125, 800).duration;
  assert.ok(Math.abs(seconds - expected) < 0.2, `took ${seconds}, expected ${expected}`);
});

test("an aspiration dwells at the bottom and leaves the liquid at its own speed", async () => {
  const world = fakeWorld(start());
  const aspirate = {
    ...pickUp,
    kind: "aspirate",
    attach: [],
    dwell: 1.5,
    channels: [{ name: "ch0", channel: 0, y: 150, down: -100, end: 10, leave: -90, leave_speed: 5 }],
  };
  const quick = await playOut(createPlayer(fakeWorld(start()).deps()), { ...aspirate, dwell: 0 });
  const withDwell = await playOut(createPlayer(world.deps()), aspirate);
  assert.ok(Math.abs(withDwell - quick - 1.5) < 0.05, "the dwell was not waited out");
  // 10 mm at 5 mm/s is at least 2 s, far slower than the drive's own 125 mm/s.
  const leaving = world.log.filter((e) => e.axis === 2 && e.value > -100 && e.value <= -90);
  assert.ok(leaving.length > 100, "it left the liquid at the drive's speed, not its own");
});

test("a page in the background jumps to the end and still hands the tips over", async () => {
  const world = fakeWorld(start());
  const player = createPlayer(world.deps(() => true));
  await player.play(pickUp); // resolves with no frames at all
  assert.deepEqual(world.at("ch0"), [0, 200, 10]);
  assert.equal(world.parents.tip, "shaft0");
  assert.equal(player.step(0.016), false);
});

test("speed 0 jumps to the end", async () => {
  const world = fakeWorld(start());
  const player = createPlayer(world.deps());
  player.setSpeed(0);
  await player.play(pickUp);
  assert.deepEqual(world.at("arm"), [300, 0, 0]);
});

test("a resource the page does not have is skipped, not waited for", async () => {
  const world = fakeWorld(start());
  const request = { ...pickUp, arm: { name: "gone", x: 5 } };
  await playOut(createPlayer(world.deps()), request);
  assert.deepEqual(world.at("ch0"), [0, 200, 10]);
});

test("the frame loop keeps going between one move ending and the next starting", async () => {
  const world = fakeWorld(start());
  const player = createPlayer(world.deps());
  const playing = player.play(pickUp);
  for (let i = 0; i < 2000; i++) {
    await new Promise((resolve) => setImmediate(resolve));
    if (!player.step(1 / 60)) break;
  }
  await playing;
  assert.deepEqual(world.at("ch0"), [0, 200, 10], "the loop stopped with the motion unfinished");
});

test("the profile reaches the end exactly and never overshoots", () => {
  for (const [d, v, a] of [
    [200, 400, 500],
    [5, 400, 500],
    [50, 250, null],
  ]) {
    const p = motionProfile(d, v, a);
    assert.equal(p.progress(p.duration), 1);
    for (let t = 0; t <= p.duration; t += p.duration / 50) {
      assert.ok(p.progress(t) >= 0 && p.progress(t) <= 1);
    }
  }
});
