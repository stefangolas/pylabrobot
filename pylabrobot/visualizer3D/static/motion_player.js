// Plays a motion the server read from a device command: the drives' moves, in the order the device
// makes them, each following its drive's speed profile. Pure - it is handed how to read and set
// positions and how to move a tip - so it can be checked outside a page.
//
// The stroke is the one the simulator records a tip command as: across, with the arm and the
// channels moving at once; down onto the targets; back up. Before it, anything below the traverse
// height rises to it; at the bottom, tips change hands and an aspiration dwells, then leaves the
// liquid at its own swap speed. A command that only moves one axis plays that one move.

import { motionProfile } from "./motion_profile.js";

// A move shorter than this, in mm, is not made at all.
const STILL = 0.05;

/**
 * @param {object} deps
 * @param {(index: number, axis: number) => number} deps.readAxis  where a resource is, per axis
 * @param {(index: number, axis: number, value: number) => void} deps.setAxis  put it somewhere
 * @param {(name: string) => number | undefined} deps.indexOf  a resource by name
 * @param {(name: string, parent: string | null) => void} deps.attach  hand a tip to a new holder
 * @param {() => boolean} deps.skipping  whether to jump to the end rather than play
 */
export function createPlayer({ readAxis, setAxis, indexOf, attach, skipping }) {
  let speed = 1;
  // What is moving now: one entry per axis of a resource, or a pause (index -1).
  const running = new Set();
  // Motions being played, which keep the frame loop going between one move ending and the next
  // starting.
  let playing = 0;

  function finish(entry) {
    if (entry.index >= 0) setAxis(entry.index, entry.axis, entry.to);
    running.delete(entry);
    entry.resolve();
  }

  // Move one axis of a resource to `to`, as `drive` would.
  function move(index, axis, to, drive) {
    /** @type {Promise<void>} */
    const moved = new Promise((resolve) => {
      const from = readAxis(index, axis);
      const profile = motionProfile(to - from, drive?.speed, drive?.acceleration);
      const entry = { index, axis, from, to, profile, t: 0, resolve };
      if (skipping() || !(speed > 0) || profile.duration === 0) finish(entry);
      else running.add(entry);
    });
    return moved;
  }

  function pause(seconds) {
    /** @type {Promise<void>} */
    const paused = new Promise((resolve) => {
      if (skipping() || !(speed > 0) || !(seconds > 0)) {
        resolve();
        return;
      }
      running.add({ index: -1, profile: { duration: seconds }, t: 0, resolve });
    });
    return paused;
  }

  // The phases of a motion, in order. Each looks at where things are when its turn comes and
  // returns the moves it starts together; an empty one is skipped.
  function phases(request) {
    const drives = request.drives ?? {};
    const channels = (key) =>
      (request.channels ?? [])
        .filter((c) => c[key] !== null && c[key] !== undefined)
        .map((c) => ({ ...c, index: indexOf(c.name) }))
        .filter((c) => c.index !== undefined);

    return [
      // Up to traverse height: whatever is lower rises, whatever is higher stays.
      () =>
        (request.traverse ?? [])
          .map((t) => ({ ...t, index: indexOf(t.name) }))
          .filter((t) => t.index !== undefined && readAxis(t.index, 2) < t.z - STILL)
          .map((t) => () => move(t.index, 2, t.z, drives.z)),

      // Across: the arm in X and the channels in Y, at once.
      () => {
        const moves = [];
        const arm = request.arm;
        const armIndex = arm ? indexOf(arm.name) : undefined;
        if (armIndex !== undefined && Math.abs(readAxis(armIndex, 0) - arm.x) >= STILL) {
          moves.push(() => move(armIndex, 0, arm.x, drives.x));
        }
        for (const c of channels("y")) {
          if (Math.abs(readAxis(c.index, 1) - c.y) >= STILL) {
            moves.push(() => move(c.index, 1, c.y, drives.y));
          }
        }
        return moves;
      },

      // Down onto the targets.
      () =>
        channels("down")
          .filter((c) => Math.abs(readAxis(c.index, 2) - c.down) >= STILL)
          .map((c) => () => move(c.index, 2, c.down, drives.z)),

      // At the bottom: tips change hands, and whatever the command does there takes its time.
      () => {
        const handovers = request.attach ?? [];
        if (!handovers.length && !(request.dwell > 0)) return [];
        return [
          async () => {
            for (const { name, parent } of handovers) attach(name, parent ?? null);
            await pause(request.dwell);
          },
        ];
      },

      // Out of the liquid, at the command's own speed.
      () =>
        channels("leave")
          .filter((c) => c.leave - readAxis(c.index, 2) >= STILL)
          .map(
            (c) => () =>
              move(c.index, 2, c.leave, {
                speed: c.leave_speed,
                acceleration: drives.z?.acceleration,
              }),
          ),

      // Back up, to where the command ends.
      () =>
        channels("end")
          .filter((c) => Math.abs(readAxis(c.index, 2) - c.end) >= STILL)
          .map((c) => () => move(c.index, 2, c.end, drives.z)),
    ];
  }

  return {
    setSpeed(value) {
      speed = Math.max(0, value);
    },

    /**
     * Play a motion to its end. Resolves when it has, or at once when it cannot be played.
     *
     * @param {any} request what `motion.py` read from the command
     */
    async play(request) {
      playing++;
      try {
        for (const phase of phases(request)) {
          const moves = phase();
          if (moves.length) await Promise.all(moves.map((start) => start()));
        }
      } finally {
        playing--;
      }
    },

    /**
     * Advance everything that is moving. For the frame loop; says whether anything is still
     * moving, or about to.
     *
     * @param {number} delta seconds since the last frame
     */
    step(delta) {
      const step = delta * speed;
      for (const entry of running) {
        entry.t += step;
        if (entry.t >= entry.profile.duration) {
          finish(entry);
          continue;
        }
        if (entry.index >= 0) {
          const share = entry.profile.progress(entry.t);
          setAxis(entry.index, entry.axis, entry.from + (entry.to - entry.from) * share);
        }
      }
      return running.size > 0 || playing > 0;
    },

    /** Bring everything moving to where it was going, at once. */
    finishAll() {
      for (const entry of [...running]) finish(entry);
    },

    /** Drop everything moving where it stands: the scene it was moving in is gone. */
    dropAll() {
      for (const entry of [...running]) {
        running.delete(entry);
        entry.resolve();
      }
    },
  };
}
