"""What iSWAP transport plans sweep through, on a simulated STARlet's demo deck."""

import time
import unittest

from pylabrobot.hamilton.star.driver.features.iswap_collisions import (
  Joints,
  Kinematics,
  check_plan,
  joints_now,
  sweeps,
)
from pylabrobot.hamilton.star.driver.features.iswap_transport import iSWAPTransport
from pylabrobot.resources.collision import distance, solid_pieces
from pylabrobot.resources.tip_rack import TipRack
from pylabrobot.resources.tip_tracking import does_tip_tracking, set_tip_tracking
from pylabrobot.visualizer3D.demo import build_facility, star_of


class iSWAPCollisionTests(unittest.IsolatedAsyncioTestCase):
  async def asyncSetUp(self) -> None:
    was = does_tip_tracking()
    set_tip_tracking(True)
    self.addCleanup(set_tip_tracking, was)
    self.facility = build_facility()
    self.star = star_of(self.facility)
    self.deck = self.star.deck
    self.deck.get_resource("destination_1").unassign()
    await self.star.setup()
    iswap = self.star.iswap
    assert iswap is not None
    self.iswap = iswap
    self.transport = iSWAPTransport(iswap)
    self.site = self.deck.get_resource("destination_carrier").children[1]

  def obstacles(self, plan) -> set:
    return {c.obstacle.name for c in check_plan(self.transport, plan)}

  async def test_what_the_sweeps_end_on_is_where_the_model_puts_the_parts(self):
    await self.iswap.make_space()
    plate = self.deck.get_resource("source_1")
    for plan_it in (
      lambda: self.transport.plan_pick_up(plate, direction="back"),
      lambda: self.transport.plan_drop(self.site, direction="left"),
    ):
      plan = plan_it()
      swept = sweeps(self.transport, plan)
      predicted = []
      for group in swept.groups:
        last = group.segments[-1].poses[-1]
        predicted += [(p.resource, [last.apply(q) for q in p.points]) for p in group.pieces]
      await self.transport.execute(plan)
      for resource, points in predicted:
        now = {tuple(round(v, 6) for v in p.points[0]): p for p in solid_pieces(resource)}
        best = min(
          max(abs(a - b) for q, r in zip(piece.points, points) for a, b in zip(q, r))
          for piece in now.values()
        )
        self.assertLess(best, 0.1, resource.name)

  async def test_no_point_of_a_turn_strays_further_from_its_hulls_than_their_slack(self):
    await self.iswap.make_space()
    plan = self.transport.plan_pick_up(self.deck.get_resource("source_1"), direction="back")
    swept = sweeps(self.transport, plan)
    kin = Kinematics(self.transport, joints_now(self.transport))
    gripper = next(g for g in swept.groups if g.name == "iSWAP gripper")
    turning = [s for s in gripper.segments if s.slack > 0]
    self.assertTrue(turning)
    # The way is walked from the joints themselves: a big turn, cut as the sweeps cut it.
    now = joints_now(self.transport)
    target = Joints(now.x, now.y, now.z, now.elbow - 90.0, now.wrist + 60.0)
    n, slack = kin.arcs(now, target)
    for k in range(0, n, max(1, n // 10)):
      ends = [
        now.but(
          elbow=now.elbow + (target.elbow - now.elbow) * f,
          wrist=now.wrist + (target.wrist - now.wrist) * f,
        )
        for f in (k / n, (k + 1) / n)
      ]
      for piece in gripper.pieces:
        hull = [kin.gripper(j).apply(q) for j in ends for q in piece.points]
        for m in range(1, 10):
          f = (k + m / 10) / n
          j = now.but(
            elbow=now.elbow + (target.elbow - now.elbow) * f,
            wrist=now.wrist + (target.wrist - now.wrist) * f,
          )
          for q in piece.points:
            self.assertLessEqual(distance([kin.gripper(j).apply(q)], hull), slack + 1e-9)

  async def test_a_plate_moved_at_the_fixed_height_hits_nothing(self):
    await self.iswap.make_space()
    plate = self.deck.get_resource("source_1")
    pick = self.transport.plan_pick_up(plate, direction="front")
    self.assertEqual(self.obstacles(pick), set())
    await self.transport.execute(pick)
    self.assertEqual(self.obstacles(self.transport.plan_drop(self.site, direction="front")), set())

  async def test_a_plate_turned_a_quarter_onto_a_landscape_site_meets_its_neighbour(self):
    # PyLabRobot places it; the plate is 127.8 mm deep turned, the sites 96 mm apart.
    await self.iswap.make_space()
    await self.transport.pick_up_resource(self.deck.get_resource("source_1"), direction="front")
    drop = self.transport.plan_drop(self.site, direction="left")
    self.assertIn("destination_2", self.obstacles(drop))

  async def test_carried_too_low_it_sweeps_through_what_the_fixed_height_clears(self):
    await self.iswap.make_space()
    source_3 = self.deck.get_resource("source_3")
    await self.transport.pick_up_resource(source_3, direction="front", end_height=205.0)
    self.assertEqual(self.obstacles(self.transport.plan_drop(self.site)), set())
    low = self.transport.plan_drop(self.site, traverse_height=205.0)
    self.assertIn("source_2", self.obstacles(low))

  async def test_the_elbow_nearest_the_joints_can_bring_link_1_down_onto_a_tip_rack(self):
    await self.iswap.make_space()
    plate = self.deck.get_resource("source_3")
    right = self.transport.plan_pick_up(plate, direction="front", elbow="right")
    self.assertIn("tips_2", self.obstacles(right))
    front = self.transport.plan_pick_up(plate, direction="front", elbow="front")
    self.assertNotIn("tips_2", self.obstacles(front))

  async def test_tips_on_the_channels_are_in_the_way_and_the_housing_is_not(self):
    rack = self.deck.get_resource("tips_0")
    assert isinstance(rack, TipRack) and self.star.pipettes is not None
    await self.star.pipettes.pick_up_tips([rack.get_item(f"{row}1") for row in "ABCDEFGH"])
    plan = self.transport.plan_pick_up(self.deck.get_resource("source_1"), direction="front")
    hits = check_plan(self.transport, plan)
    mounted = {c.obstacle.name for c in hits if c.obstacle.parent is not None}
    self.assertTrue(any(name.startswith("tips_0_tipspot_") for name in mounted))
    self.assertFalse(any("housing" in c.obstacle.name for c in hits))

  async def test_a_check_is_quick(self):
    await self.iswap.make_space()
    plan = self.transport.plan_pick_up(self.deck.get_resource("source_1"), direction="back")
    t = time.perf_counter()
    check_plan(self.transport, plan)
    self.assertLess(time.perf_counter() - t, 3.0)


if __name__ == "__main__":
  unittest.main()
