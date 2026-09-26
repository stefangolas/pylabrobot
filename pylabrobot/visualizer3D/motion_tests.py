"""The motion channel, checked without a browser.

What a command is read as (`motion.py`), and how the server holds a command until the pages have
played it, against a simulated STAR and pages that are only websocket clients. The player itself is
checked in Node (`motion_player_tests.mjs`), run from here where Node is installed.
"""

import asyncio
import json
import pathlib
import shutil
import subprocess
import time
import unittest
from typing import Any, Dict, List, Optional

import websockets

from pylabrobot.resources.plate import Plate
from pylabrobot.resources.tip_rack import TipRack
from pylabrobot.resources.tip_tracking import does_tip_tracking, set_tip_tracking
from pylabrobot.visualizer3D.demo import build_facility, fill, star_of
from pylabrobot.visualizer3D.motion import star_motion
from pylabrobot.visualizer3D.server import Viewer3D
from pylabrobot.visualizer3D.server_tests import free_ports, track_volumes

HERE = pathlib.Path(__file__).parent
NODE = shutil.which("node")


async def simulated_star(test: unittest.TestCase) -> Any:
  """The demo facility's STAR, set up, tracking volumes and tips."""
  track_volumes(test)
  was_tracking = does_tip_tracking()
  set_tip_tracking(True)
  test.addCleanup(set_tip_tracking, was_tracking)
  facility = build_facility()
  star = star_of(facility)
  await star.setup()
  return facility, star


class DecoderTests(unittest.IsolatedAsyncioTestCase):
  """A command is read for where it takes the drives, which is where the model then has them."""

  async def asyncSetUp(self) -> None:
    self.facility, self.star = await simulated_star(self)
    self.requests: List[Dict[str, Any]] = []

    async def listen(module: str, command: str, params: Dict[str, Any]) -> None:
      request = star_motion(self.star.driver, module, command, params)
      if request is not None:
        self.requests.append(request)

    self.star.driver.motion_listener = listen
    self.rack = self.star.deck.get_resource("tips_0")
    self.source = self.star.deck.get_resource("source_0")
    assert isinstance(self.rack, TipRack) and isinstance(self.source, Plate)
    fill(self.source, 300.0)

  def assert_ends_where_the_model_is(self, request: Dict[str, Any]) -> None:
    arm = self.star.x_arm.resource
    if request["arm"] is not None:
      self.assertAlmostEqual(request["arm"]["x"], arm.location.x, delta=0.1, msg="arm")
    channels = {c.name: c for c in self.star.pipettes.resources}
    for target in request["channels"]:
      at = channels[target["name"]].location
      if target.get("y") is not None:
        self.assertAlmostEqual(target["y"], at.y, delta=0.1, msg=f"{target['name']} y")
      if target.get("end") is not None:
        self.assertAlmostEqual(target["end"], at.z, delta=0.1, msg=f"{target['name']} z")

  async def test_each_command_ends_where_the_model_records_it_ending(self):
    spots = [self.rack.get_item(f"{row}1") for row in "ABCDEFGH"]
    wells = [self.source.get_item(f"{row}1") for row in "ABCDEFGH"]
    for operation, kind in (
      (lambda: self.star.pipettes.pick_up_tips(spots), "tip_pickup"),
      (lambda: self.star.pipettes.aspirate(wells, [50.0] * 8), "aspirate"),
      (lambda: self.star.pipettes.drop_tips(spots), "tip_drop"),
    ):
      self.requests.clear()
      await operation()
      stroke = [r for r in self.requests if r["kind"] == kind]
      self.assertEqual(len(stroke), 1, f"{kind}: {[r['kind'] for r in self.requests]}")
      self.assert_ends_where_the_model_is(stroke[0])

  async def test_the_tips_that_change_hands_are_named(self):
    spots = [self.rack.get_item(f"{row}2") for row in "AB"]
    tips = [spot.tip.name for spot in spots]
    await self.star.pipettes.pick_up_tips(spots)
    pick_up = next(r for r in self.requests if r["kind"] == "tip_pickup")
    shafts = [c.children[0].name for c in self.star.pipettes.resources[:2]]
    self.assertEqual(pick_up["attach"], [{"name": t, "parent": s} for t, s in zip(tips, shafts)])

    await self.star.pipettes.drop_tips(spots)
    drop = next(r for r in self.requests if r["kind"] == "tip_drop")
    self.assertEqual(drop["attach"], [{"name": t, "parent": s.name} for t, s in zip(tips, spots)])

  async def test_an_aspiration_dwells_as_long_as_its_volume_takes(self):
    await self.star.pipettes.pick_up_tips([self.rack.get_item("A3")])
    await self.star.pipettes.aspirate([self.source.get_item("A3")], [100.0])
    aspirate = next(r for r in self.requests if r["kind"] == "aspirate")
    self.assertGreater(aspirate["dwell"], 0.0)
    self.assertEqual(aspirate["drives"]["z"]["speed"], self.star.pipettes.default_z_speed)
    self.assertEqual(aspirate["drives"]["y"]["speed"], self.star.pipettes.default_y_speed)

  async def test_a_read_moves_nothing(self):
    self.assertIsNone(star_motion(self.star.driver, "C0", "RY", {}))
    self.assertIsNone(star_motion(self.star.driver, "C0", "XX", {}))


class FakePage:
  """A page that is only a websocket: it plays each motion by waiting `delay` seconds."""

  def __init__(self, viewer: Viewer3D, delay: Optional[float]):
    self.viewer = viewer
    self.delay = delay  # None: never says it is done
    self.events: List[str] = []
    self._socket: Any = None
    self._task: Optional["asyncio.Task[None]"] = None

  async def open(self) -> "FakePage":
    self._socket = await websockets.connect(self.viewer.ws_url, max_size=None)
    await self._socket.send(json.dumps({"event": "hello", "data": {"backend": "none"}}))
    self._task = asyncio.ensure_future(self._listen())
    while "scene" not in self.events:
      await asyncio.sleep(0.01)
    return self

  async def _listen(self) -> None:
    try:
      async for message in self._socket:
        parsed = json.loads(message)
        kind, data = parsed["event"], parsed["data"]
        self.events.append(kind)
        if kind == "state" and data.get("locations"):
          self.events.append("locations")
          self.events.extend(f"at:{name}" for name in data["locations"])
        if kind == "motion" and self.delay is not None:
          asyncio.ensure_future(self._play(data["id"]))
    except websockets.ConnectionClosed:
      pass

  async def _play(self, motion_id: int) -> None:
    await asyncio.sleep(self.delay or 0.0)
    await self._socket.send(json.dumps({"event": "motion_done", "data": {"id": motion_id}}))

  async def close(self) -> None:
    await self._socket.close()
    if self._task is not None:
      await self._task


class ServerTests(unittest.IsolatedAsyncioTestCase):
  """A command waits until every page has played it, and for nothing when there is nobody."""

  async def asyncSetUp(self) -> None:
    self.facility, self.star = await simulated_star(self)
    fs_port, ws_port = free_ports(2)
    self.viewer = Viewer3D(self.facility, open_browser=False, fs_port=fs_port, ws_port=ws_port)
    await self.viewer.start()
    self.viewer.attach_motion(self.star.driver)
    self.addAsyncCleanup(self.viewer.stop)
    self.rack = self.star.deck.get_resource("tips_0")
    assert isinstance(self.rack, TipRack)

  async def page(self, delay: Optional[float]) -> FakePage:
    page = await FakePage(self.viewer, delay).open()
    self.addAsyncCleanup(page.close)
    return page

  async def timed_pick_up(self, well: str = "A1") -> float:
    began = time.monotonic()
    await self.star.pipettes.pick_up_tips([self.rack.get_item(well)])
    return time.monotonic() - began

  async def test_a_command_waits_for_the_page(self):
    page = await self.page(0.5)
    self.assertGreaterEqual(await self.timed_pick_up(), 0.5)
    self.assertIn("motion", page.events)

  async def test_the_slowest_page_sets_the_pace(self):
    await self.page(0.1)
    await self.page(0.6)
    self.assertGreaterEqual(await self.timed_pick_up(), 0.6)

  async def test_with_no_page_nothing_waits(self):
    self.assertLess(await self.timed_pick_up(), 0.5)

  async def test_a_page_that_leaves_lets_the_command_go(self):
    page = await self.page(None)  # never answers
    asyncio.get_running_loop().call_later(0.3, lambda: asyncio.ensure_future(page.close()))
    self.assertLess(await self.timed_pick_up(), 5.0)

  async def test_a_motion_starts_from_where_the_last_command_left_things(self):
    """The model moves when a command ends; the next motion is played from there, so what that
    move changed has to reach the page first."""
    page = await self.page(0.05)
    await self.timed_pick_up("A1")
    await self.star.pipettes.drop_tips([self.rack.get_item("A1")])
    motions = [i for i, kind in enumerate(page.events) if kind == "motion"]
    self.assertGreaterEqual(len(motions), 2)
    between = page.events[motions[0] + 1 : motions[-1]]
    # The pick-up took a tip onto a shaft, a change of shape, which carries the positions with it.
    self.assertIn("moves", between, f"the pick-up reached the page too late: {page.events}")


class ISWAPDecoderTests(unittest.IsolatedAsyncioTestCase):
  """An iSWAP command is read for the drives it moves, which is where the model then has them."""

  async def asyncSetUp(self) -> None:
    self.facility, self.star = await simulated_star(self)
    self.iswap = self.star.iswap
    self.requests: List[Dict[str, Any]] = []

    async def listen(module: str, command: str, params: Dict[str, Any]) -> None:
      request = star_motion(self.star.driver, module, command, params)
      if request is not None:
        self.requests.append(request)

    self.star.driver.motion_listener = listen
    await self.iswap.make_space()
    self.parked = await self.iswap.elbow_request_y_position()

  def last(self, kind: str) -> Dict[str, Any]:
    return [r for r in self.requests if r["kind"] == kind][-1]

  async def test_the_head_moves_where_the_model_puts_it(self):
    await self.iswap.elbow_move_to_y_position(self.parked - 150.0)
    await self.iswap.elbow_move_to_z_position(250.0)
    head = self.iswap.resource
    moves = [r["moves"][0] for r in self.requests if r["kind"] == "iswap_move"]
    along_y, along_z = moves[-2], moves[-1]
    self.assertEqual((along_y["axis"], along_z["axis"]), (1, 2))
    self.assertAlmostEqual(along_y["to"], head.location.y, delta=0.05)
    self.assertAlmostEqual(along_z["to"], head.location.z, delta=0.05)
    self.assertGreater(along_y["speed"], 0)

  async def test_a_joint_turns_to_the_rotation_the_model_gives_it(self):
    await self.iswap.elbow_move_to_y_position(self.parked - 200.0)
    await self.iswap.rotate_to_angles(elbow_absolute_angle="front", gripper_absolute_angle="left")
    turns = {t["name"]: t for t in self.last("iswap_turn")["turns"]}
    for resource in (self.iswap.link_1, self.iswap.gripper):
      turn = turns[resource.name]
      self.assertAlmostEqual((turn["drive"] - turn["base"]) % 360, resource.rotation.z % 360, 3)
      self.assertEqual(turn["pivot"]["x"], resource.proximal_joint.x)
      self.assertGreater(turn["speed"], 0)

  async def test_the_fingers_stand_where_the_model_stands_them(self):
    await self.iswap.gripper_move_to_jaw_position(90.0)
    jaws = self.last("iswap_jaws")["jaws"]
    for finger, target in zip(self.iswap.gripper.fingers, jaws["fingers"]):
      self.assertEqual(target["name"], finger.name)
      self.assertAlmostEqual(target["y"], finger.location.y, delta=0.01)
    self.assertEqual(jaws["gripper"], self.iswap.gripper.name)


class ISWAPServerTests(unittest.IsolatedAsyncioTestCase):
  async def test_a_move_the_model_records_first_is_played_before_it_is_told(self):
    """The iSWAP writes a move's target before sending it. Told first, the page would put the head
    at the end of the move and have nothing left to play."""
    facility, star = await simulated_star(self)
    fs_port, ws_port = free_ports(2)
    viewer = Viewer3D(facility, open_browser=False, fs_port=fs_port, ws_port=ws_port)
    await viewer.start()
    self.addAsyncCleanup(viewer.stop)
    viewer.attach_motion(star.driver)
    await star.iswap.make_space()
    y = await star.iswap.elbow_request_y_position()
    page = await FakePage(viewer, 0.05).open()
    self.addAsyncCleanup(page.close)
    head = f"at:{star.iswap.resource.name}"
    before = len(page.events)
    await star.iswap.elbow_move_to_y_position(y - 100.0)
    for _ in range(100):
      if head in page.events[before:]:
        break
      await asyncio.sleep(0.02)
    after = page.events[before:]
    self.assertIn("motion", after)
    self.assertIn(head, after)
    self.assertLess(after.index("motion"), after.index(head), after)


@unittest.skipUnless(NODE, "no Node to run the player's tests")
class PlayerTests(unittest.TestCase):
  def test_the_player(self):
    result = subprocess.run(
      [str(NODE), "--test", str(HERE / "motion_player_tests.mjs")],
      capture_output=True,
      text=True,
      timeout=120,
    )
    self.assertEqual(result.returncode, 0, result.stdout[-3000:] + result.stderr[-2000:])


if __name__ == "__main__":
  unittest.main()
