import asyncio
import struct
import unittest
from unittest.mock import AsyncMock

from pylabrobot.hamilton.mpe2 import (
  ControlPoint,
  ControlPointType,
  MPE2Driver,
  MPE2Error,
  MPE2SimulationDriver,
  SPEControlState,
  WasteContainer,
  parse_control_points,
)
from pylabrobot.hamilton.mpe2 import commands as C
from pylabrobot.hamilton.transport.tcp.packets import Address

DEST = Address(1, 1, 0x1000)
S = SPEControlState


def f32(v):
  return bytes([40, 0, 4, 0]) + struct.pack("<f", v)


def u32(v):
  return bytes([6, 0, 4, 0]) + struct.pack("<I", v)


def enum(v):
  return bytes([32, 0, 4, 0]) + struct.pack("<I", v)


def boolean(v):  # odd-length fragments are padded to even, with the padded flag set
  return bytes([23, 1, 2, 0, int(v), 0])


class TestEncoding(unittest.TestCase):
  """Parameters as the instrument definition lays them out: interface 1, these method ids."""

  def test_ids(self):
    ids = {
      C.Initialize: 21,
      C.InitializeWithoutWaste: 18,
      C.FilterPlatePlaced: 7,
      C.FilterPlateRemoved: 8,
      C.ClampFilterPlate: 9,
      C.RetrieveFilterPlate: 10,
      C.CollectionPlatePlaced: 11,
      C.CollectionPlateRemoved: 12,
      C.ProcessFilterPlateToWaste: 23,
      C.ProcessFilterPlateToCollection: 14,
      C.Abort: 15,
      C.GetControlState: 1,
      C.GetLabwareParameters: 2,
      C.GetControlPointRanges: 4,
      C.GetManifoldInformation: 5,
      C.GetIsInitialized: 17,
      C.GetCompletionStatus: 19,
    }
    for command, method in ids.items():
      self.assertEqual(
        (getattr(command, "interface_id"), getattr(command, "command_id")),
        (1, method),
        command.__name__,
      )

  def test_filter_plate_placed(self):
    p = C.FilterPlatePlaced(dest=DEST, filter_height=31.35, nozzle_height=38.4).build_parameters()
    self.assertEqual(p.build(), f32(31.35) + f32(38.4))

  def test_initialize(self):
    p = C.Initialize(dest=DEST, waste_container=WasteContainer.CONTAINER_2).build_parameters()
    self.assertEqual(p.build(), boolean(True) + u32(10000) + u32(10000) + enum(1) + boolean(False))

  def test_process_to_waste(self):
    points = (ControlPoint(60.0, ControlPointType.PRESSURE, 0.5),)
    p = C.ProcessFilterPlateToWaste(dest=DEST, control_points=points).build_parameters().build()
    point = f32(60.0) + enum(1) + f32(0.5)
    structure = bytes([30, 0]) + struct.pack("<H", len(point)) + point
    array = bytes([31, 0]) + struct.pack("<H", len(structure)) + structure
    self.assertEqual(p, array + boolean(True) + enum(0) + boolean(False))

  def test_status_requests_are_status_actions(self):
    self.assertNotEqual(C.GetCompletionStatus.action_code, C.ClampFilterPlate.action_code)


class TestControlPoints(unittest.TestCase):
  def test_nist_lysate_clearing(self):
    points = parse_control_points("pressure,20,240;pressure,65,60;", number_of_ports=96)
    self.assertEqual([p.type for p in points], [ControlPointType.PRESSURE] * 2)
    self.assertEqual([p.duration for p in points], [240.0, 60.0])
    self.assertAlmostEqual(points[0].value, 20 / 96)

  def test_like_venus(self):
    self.assertEqual(
      parse_control_points(" idle, 0, 5 ", 24), [ControlPoint(5.0, ControlPointType.NONE, 0.0)]
    )
    self.assertEqual(parse_control_points("FLOW,48,1;", 48)[0].type, ControlPointType.FLOW)
    for bad in ("pressure,20", "pressure;20;240", "vacuum,1,1;"):
      with self.assertRaises(ValueError):
        parse_control_points(bad, 96)


class TestDriver(unittest.TestCase):
  def test_waits_for_completion(self):
    client = AsyncMock()
    client.resolve_path.return_value = DEST
    client.execute.side_effect = [C.ManifoldInfo("x", "y", 96), None, False, False, True]
    d = MPE2Driver("host", 0, poll_interval=0, client=client)
    asyncio.run(d.setup())
    asyncio.run(d.clamp_filter_plate())
    sent = [type(call.args[0]) for call in client.execute.call_args_list]
    self.assertEqual(
      sent, [C.GetManifoldInformation, C.ClampFilterPlate] + [C.GetCompletionStatus] * 3
    )
    self.assertEqual(d.number_of_ports, 96)

  def test_method_strings_use_the_port_count(self):
    client = AsyncMock()
    client.resolve_path.return_value = DEST
    client.execute.side_effect = [C.ManifoldInfo("x", "y", 24), None, True]
    d = MPE2Driver("host", 0, poll_interval=0, client=client)
    asyncio.run(d.setup())
    asyncio.run(d.process_filter_plate_to_waste("pressure,40,60;"))
    command = client.execute.call_args_list[1].args[0]
    self.assertAlmostEqual(command.control_points[0].value, 40 / 24)


class TestSimulation(unittest.TestCase):
  def run_steps(self, d, *steps):
    for name, kwargs in steps:
      asyncio.run(getattr(d, name)(**kwargs))

  def test_nist_dna_extraction(self):
    """The MPE² calls of the NIST DNA Extraction, in order.

    Stages 04-07 each run the method's `FilterPlateToWaste` wrapper: placed, to waste with the plate
    returned, removed. Stage 04's "filter plate" is the filter plate stacked on the receiving plate,
    86.5 mm together, so the lysate collects in the receiving plate under it. Stage 08 clamps the
    binding plate, then places the elution plate under it and presses to collection.
    """
    d = MPE2SimulationDriver()
    seen: list = []
    d.add_state_observer(seen.append)

    def to_waste(f, n, points):
      return [
        ("filter_plate_placed", {"filter_height": f, "nozzle_height": n}),
        ("process_filter_plate_to_waste", {"control_points": points}),
        ("filter_plate_removed", {}),
      ]

    self.run_steps(
      d,
      ("initialize", {}),
      *to_waste(86.5, 86.5, "pressure,20,240;pressure,65,60;"),
      *to_waste(31.35, 38.4, "pressure,40,60;"),
      *to_waste(31.35, 38.4, "pressure,40,60;"),
      *to_waste(31.35, 38.4, "pressure,40,60;pressure,65,420;"),
      ("filter_plate_placed", {"filter_height": 31.35, "nozzle_height": 38.4}),
      ("clamp_filter_plate", {}),
      ("collection_plate_placed", {"collection_plate_height": 14.35, "offset_from_nozzles": 0}),
      (
        "process_filter_plate_to_collection",
        {"control_points": "pressure,65,420;", "return_filter_plate_to_integration_area": False},
      ),
      ("collection_plate_removed", {}),
      ("retrieve_filter_plate", {}),
      ("filter_plate_removed", {}),
    )
    self.assertEqual(d.state, S.READY)
    self.assertEqual([p[0] for p in d.processed], ["waste"] * 4 + ["collection"])
    self.assertIn(S.PROCESS_FILTER_PLATE_TO_COLLECTION, seen)
    self.assertEqual(seen.count(S.CLAMPING_FILTER_PLATE_1), 5)  # four presses to waste, one clamp

  def test_refuses_out_of_state(self):
    d = MPE2SimulationDriver()
    with self.assertRaises(MPE2Error):
      asyncio.run(d.clamp_filter_plate())  # uninitialized
    self.run_steps(d, ("initialize", {}))
    with self.assertRaises(MPE2Error):
      asyncio.run(d.process_filter_plate_to_collection("pressure,20,1;"))  # no plates
    self.run_steps(d, ("filter_plate_placed", {"filter_height": 30, "nozzle_height": 38}))
    with self.assertRaises(MPE2Error):
      asyncio.run(d.process_filter_plate_to_collection("pressure,20,1;"))  # no collection plate

  def test_left_clamped(self):
    d = MPE2SimulationDriver()
    self.run_steps(
      d,
      ("initialize", {}),
      ("filter_plate_placed", {"filter_height": 30, "nozzle_height": 38}),
      (
        "process_filter_plate_to_waste",
        {"control_points": "pressure,40,1;", "return_filter_plate_to_integration_area": False},
      ),
    )
    self.assertEqual(d.state, S.FILTER_PLATE_CLAMPED)
    self.run_steps(d, ("retrieve_filter_plate", {}))
    self.assertEqual(d.state, S.FILTER_PLATE_PLACED)

  def test_range(self):
    d = MPE2SimulationDriver(number_of_ports=1)
    self.run_steps(
      d, ("initialize", {}), ("filter_plate_placed", {"filter_height": 30, "nozzle_height": 38})
    )
    with self.assertRaises(MPE2Error):
      asyncio.run(d.process_filter_plate_to_waste("pressure,400,1;"))


if __name__ == "__main__":
  unittest.main()
