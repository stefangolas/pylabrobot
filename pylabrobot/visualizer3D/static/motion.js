// Acting out what a device's drives do between the positions PyLabRobot records.
//
// PyLabRobot sends a device a command and records where it ends up; the device's own motion
// controller decides how to get there. The server reads each command for its targets (see
// `motion.py`) and sends them here as a motion, which `motion_player.js` plays; the server is told
// when it is done. Python holds the command until then, so the model moves only once the picture
// has got there.

import { readAxis, reattach, setAxis } from "./live.js";
import { createPlayer } from "./motion_player.js";
import { world } from "./world.js";

const player = createPlayer({
  readAxis,
  setAxis,
  indexOf: (name) => world?.indexOfName.get(name),
  attach: reattach,
  // A tab in the background gets no frames, so nothing it played would ever finish and the
  // command would wait out its timeout. It jumps instead.
  skipping: () => document.hidden,
});

// How fast motions play against the drives' own speeds: `?motion=2` twice as fast, `?motion=0`
// not at all - everything jumps to where it ends and the command goes straight on.
const asked = Number(new URLSearchParams(location.search).get("motion") ?? 1);
player.setSpeed(Number.isFinite(asked) && asked >= 0 ? asked : 1);

export const stepMotion = (delta) => player.step(delta);
export const dropMotions = () => player.dropAll();

document.addEventListener("visibilitychange", () => {
  if (document.hidden) player.finishAll();
});

/**
 * Play a motion the server sent, then say so. The command waits for that, so it is said whatever
 * happens: a motion that cannot be played is reported played at once.
 *
 * @param {any} request what `motion.py` read from the command
 * @param {() => void} done tells the server
 */
export async function playMotion(request, done) {
  try {
    if (world) await player.play(request);
  } catch (error) {
    console.warn("a motion could not be played", error);
  } finally {
    done();
  }
}
