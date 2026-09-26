// What a gripper takes hold of when its jaws close, and what a plate it lets go of comes to rest on.
//
// PyLabRobot does not move a plate when the iSWAP grips it, so the page does: the plate is handed to
// the gripper when the jaws close on it, rides the arm, and is handed to the site under it when they
// open. Pure - it is given boxes, not the scene - so it can be checked outside a page.

// What an arm picks up: labware, not what labware holds or what holds it.
export const MOVABLE = new Set([
  "plate",
  "lid",
  "tip_rack",
  "tube_rack",
  "plate_adapter",
  "trough",
]);

// What a plate is set down on.
export const SITES = new Set(["resource_holder", "plate_holder", "plate_adapter"]);

// How far a point may lie outside a box and still be taken as in it, in mm.
const REACH = 2;
// How far above a site a plate may be let go of and still land on it, in mm.
const DROP = 30;
// How far a site's surface may stand above the plate's bottom: a plate's skirt sits down into its
// site, 3 mm on the demo's carriers.
const SUNK = 10;

/**
 * @typedef {object} Candidate
 * @property {number} index
 * @property {string} category
 * @property {{min: {x: number, y: number, z: number}, max: {x: number, y: number, z: number}}} box
 */

const inside = (p, box, pad) =>
  p.x >= box.min.x - pad &&
  p.x <= box.max.x + pad &&
  p.y >= box.min.y - pad &&
  p.y <= box.max.y + pad &&
  p.z >= box.min.z - pad &&
  p.z <= box.max.z + pad;

const volume = (box) => (box.max.x - box.min.x) * (box.max.y - box.min.y) * (box.max.z - box.min.z);

/**
 * The labware at the point the jaws close on: the smallest movable thing whose box holds it.
 *
 * @param {{x: number, y: number, z: number}} point in world mm
 * @param {Candidate[]} candidates
 * @returns {number | undefined}
 */
export function heldAt(point, candidates) {
  let best;
  let smallest = Number.POSITIVE_INFINITY;
  for (const c of candidates) {
    if (!MOVABLE.has(c.category) || !inside(point, c.box, REACH)) continue;
    const v = volume(c.box);
    if (v < smallest) {
      smallest = v;
      best = c.index;
    }
  }
  return best;
}

/**
 * The site a plate let go of lands on: the highest one under its middle whose surface is near its
 * bottom - a little above it, as a skirt sits down into a site, or a drop's height below it.
 *
 * @param {{min: {x: number, y: number, z: number}, max: {x: number, y: number, z: number}}} box the
 *   plate's, in world mm
 * @param {Candidate[]} candidates
 * @param {number} [self] the plate's own index, which is not a site for itself
 * @returns {number | undefined}
 */
export function siteUnder(box, candidates, self) {
  const middle = { x: (box.min.x + box.max.x) / 2, y: (box.min.y + box.max.y) / 2 };
  let best;
  let highest = Number.NEGATIVE_INFINITY;
  for (const c of candidates) {
    if (c.index === self || !SITES.has(c.category)) continue;
    const b = c.box;
    const under =
      middle.x >= b.min.x - REACH &&
      middle.x <= b.max.x + REACH &&
      middle.y >= b.min.y - REACH &&
      middle.y <= b.max.y + REACH;
    const top = b.max.z;
    if (!under || top > box.min.z + SUNK || top < box.min.z - DROP) continue;
    if (top > highest) {
      highest = top;
      best = c.index;
    }
  }
  return best;
}
