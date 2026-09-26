// Plays a motion the server read from a device command: the drives' moves, in the order the device
// makes them, each following its drive's speed profile. Pure - it is handed how to read and set
// positions and how to move a tip - so it can be checked outside a page.
//
// The stroke is the one the simulator records a tip command as: across, with the arm and the
// channels moving at once; down onto the targets; back up. Before it, anything below the traverse
// height rises to it; at the bottom, tips change hands and an aspiration dwells, then leaves the
// liquid at its own swap speed. A command that only moves one axis plays that one move.
//
// An iSWAP command moves its drives at once: the head along Y or Z, the two joints turning about
// their pivots, or the jaws. Jaws that close take hold of what is between them; jaws that open let
// go of it first.

import { motionProfile } from "./motion_profile.js";

// A move shorter than this, in mm, is not made at all.
const STILL = 0.05;

/**
 * Where a resource sits once turned about Z from `from` to `to` degrees, keeping `pivot` - a point
 * in its own frame - where it was: what `Resource.rotate_to(z=..., pivot_coordinate=...)` does.
 *
 * @param {{x: number, y: number, z: number}} location relative to its parent, before the turn
 * @param {number} from degrees
 * @param {number} to degrees
 * @param {{x: number, y: number, z: number}} pivot
 * @returns {{x: number, y: number, z: number}}
 */
export function turnedLocation(location, from, to, pivot) {
  const a = (from * Math.PI) / 180;
  const b = (to * Math.PI) / 180;
  // Where the pivot is in the parent's frame, which the turn keeps.
  const px = location.x + Math.cos(a) * pivot.x - Math.sin(a) * pivot.y;
  const py = location.y + Math.sin(a) * pivot.x + Math.cos(a) * pivot.y;
  return {
    x: px - (Math.cos(b) * pivot.x - Math.sin(b) * pivot.y),
    y: py - (Math.sin(b) * pivot.x + Math.cos(b) * pivot.y),
    z: location.z,
  };
}

/**
 * @param {object} deps
 * @param {(index: number, axis: number) => number} deps.readAxis  where a resource is, per axis
 * @param {(index: number, axis: number, value: number) => void} deps.setAxis  put it somewhere
 * @param {(name: string) => number | undefined} deps.indexOf  a resource by name
 * @param {(name: string, parent: string | null, placed?: any) => void} deps.attach  hand a tip
 *   to a new holder, at `placed` ({location, rotation}) when given, else where it stands
 * @param {() => boolean} deps.skipping  whether to jump to the end rather than play
 * @param {(index: number, degrees: number, pivot: any) => void} [deps.turnTo]  turn about a pivot
 * @param {(gripper: string, point: any) => void} [deps.grip]  take hold of what is at `point`
 * @param {(gripper: string) => void} [deps.release]  let go of what the gripper holds
 */
export function createPlayer({
  readAxis,
  setAxis,
  indexOf,
  attach,
  skipping,
  turnTo = () => {},
  grip = () => {},
  release = () => {},
}) {
  let speed = 1;
  // What is moving now: one entry per axis of a resource or joint, or a pause (no `apply`).
  const running = new Set();
  // Motions being played, which keep the frame loop going between one move ending and the next
  // starting.
  let playing = 0;

  function finish(entry) {
    entry.apply?.(entry.to);
    running.delete(entry);
    entry.resolve();
  }

  // Take a value from `from` to `to` as `drive` would, handing each step to `apply`.
  function tween(from, to, drive, apply) {
    /** @type {Promise<void>} */
    const moved = new Promise((resolve) => {
      const profile = motionProfile(to - from, drive?.speed, drive?.acceleration);
      const entry = { from, to, profile, t: 0, resolve, apply };
      if (skipping() || !(speed > 0) || profile.duration === 0) finish(entry);
      else running.add(entry);
    });
    return moved;
  }

  // Move one axis of a resource to `to`, as `drive` would.
  function move(index, axis, to, drive) {
    return tween(readAxis(index, axis), to, drive, (v) => setAxis(index, axis, v));
  }

  // Turn a joint to the angle its drive is sent to. The resource's rotation is that angle less the
  // joint's `base`, and the drive goes the way its own angles run, not the short way round.
  function turn(index, joint) {
    const from = ((((readAxis(index, 5) + joint.base + 180) % 360) + 360) % 360) - 180;
    return tween(from, joint.drive, joint, (angle) =>
      turnTo(index, angle - joint.base, joint.pivot),
    );
  }

  function pause(seconds) {
    /** @type {Promise<void>} */
    const paused = new Promise((resolve) => {
      if (skipping() || !(speed > 0) || !(seconds > 0)) {
        resolve();
        return;
      }
      running.add({ profile: { duration: seconds }, t: 0, resolve });
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
            for (const { name, parent, location, rotation } of handovers) {
              attach(name, parent ?? null, location ? { location, rotation } : undefined);
            }
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

      // A drive of the iSWAP's head, each at the command's own speed.
      () =>
        (request.moves ?? [])
          .map((m) => ({ ...m, index: indexOf(m.name) }))
          .filter(
            (m) => m.index !== undefined && Math.abs(readAxis(m.index, m.axis) - m.to) >= STILL,
          )
          .map((m) => () => move(m.index, m.axis, m.to, m)),

      // The joints, turning together about their pivots.
      () =>
        (request.turns ?? [])
          .map((joint) => ({ ...joint, index: indexOf(joint.name) }))
          .filter((joint) => joint.index !== undefined)
          .map((joint) => () => turn(joint.index, joint)),

      // The jaws: letting go before they open, taking hold once they have closed.
      () => {
        const jaws = request.jaws;
        if (!jaws) return [];
        const fingers = jaws.fingers
          .map((f) => ({ ...f, index: indexOf(f.name) }))
          .filter((f) => f.index !== undefined);
        if (!fingers.length) return [];
        // The first finger faces the grip centre from +Y, so it closes toward -Y.
        const closing = fingers[0].y < readAxis(fingers[0].index, 1) - STILL;
        const opening = fingers[0].y > readAxis(fingers[0].index, 1) + STILL;
        return [
          async () => {
            if (opening) release(jaws.gripper);
            await Promise.all(fingers.map((f) => move(f.index, 1, f.y, jaws)));
            if (closing) grip(jaws.gripper, jaws.grip_point);
          },
        ];
      },
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
        if (entry.apply) {
          const share = entry.profile.progress(entry.t);
          entry.apply(entry.from + (entry.to - entry.from) * share);
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
