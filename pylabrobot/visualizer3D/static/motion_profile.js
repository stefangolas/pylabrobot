// How far along a move a drive is at a given moment: speed up, cruise, slow down.
//
// The profile of the threejs visualizer's `calculateMotionProfile`, in mm and seconds. A move too
// short to reach cruise speed speeds up for half its length and slows down for the other half.
// Pure: no three, no page, so it can be checked on its own.

/**
 * @typedef {object} Profile
 * @property {number} duration        seconds the move takes
 * @property {(t: number) => number} progress  share of the distance covered at `t` seconds, 0..1
 */

/**
 * @param {number} distance      mm, of either sign; only its size counts
 * @param {number} speed         mm/s the drive cruises at
 * @param {number} acceleration  mm/s^2 it speeds up and slows down at
 * @returns {Profile}
 */
export function motionProfile(distance, speed, acceleration) {
  const d = Math.abs(distance);
  if (!(d > 0) || !(speed > 0)) return { duration: 0, progress: () => 1 };
  if (!(acceleration > 0)) {
    const duration = d / speed;
    return { duration, progress: (t) => clamp(t / duration) };
  }

  const tAccel = speed / acceleration;
  const dAccel = 0.5 * acceleration * tAccel * tAccel;

  if (d >= 2 * dAccel) {
    // Trapezoid: up to speed, cruise, and down again.
    const dCruise = d - 2 * dAccel;
    const tCruise = dCruise / speed;
    const duration = 2 * tAccel + tCruise;
    return {
      duration,
      progress: (t) => {
        if (t >= duration) return 1;
        if (t <= tAccel) return (0.5 * acceleration * t * t) / d;
        if (t <= tAccel + tCruise) return (dAccel + speed * (t - tAccel)) / d;
        const s = t - tAccel - tCruise;
        return clamp((dAccel + dCruise + speed * s - 0.5 * acceleration * s * s) / d);
      },
    };
  }

  // Triangle: never reaches cruise speed.
  const vPeak = Math.sqrt(acceleration * d);
  const tPeak = vPeak / acceleration;
  const duration = 2 * tPeak;
  return {
    duration,
    progress: (t) => {
      if (t >= duration) return 1;
      if (t <= tPeak) return (0.5 * acceleration * t * t) / d;
      const s = t - tPeak;
      return clamp((0.5 * d + vPeak * s - 0.5 * acceleration * s * s) / d);
    },
  };
}

function clamp(p) {
  return Math.max(0, Math.min(1, p));
}
