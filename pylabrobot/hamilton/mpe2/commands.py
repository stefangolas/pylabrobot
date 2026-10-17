"""MPE² firmware commands: the `SPEControl` object's interface 1, as HOI requests.

Method ids, parameter order and wire types are from the instrument definition embedded in
Hamilton's MPE2 HSL driver v2.1.0.0 (`Hamilton.Module.SPEMainController`). Which overload Venus
uses, and how it turns a method's control-point string into structs, are from the same driver's
`MPEFirmware` class; `parse_control_points` reproduces the latter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import IntEnum
from typing import ClassVar, List, Sequence, cast

from pylabrobot.hamilton.transport.tcp.commands import TCPCommand
from pylabrobot.hamilton.transport.tcp.messages import HoiParams, HoiParamsParser, parse_into_struct
from pylabrobot.hamilton.transport.tcp.protocol import Hoi2Action, HamiltonProtocol
from pylabrobot.hamilton.transport.tcp.wire_types import (
  F32,
  U32,
  PaddedBool,
  Str,
  StructArray,
)
from pylabrobot.hamilton.transport.tcp.wire_types import Enum as WEnum

ROOT_NAME = "SPEMainControllerRoot"
SPE_CONTROL_PATH = "SPEMainControllerRoot.SPEControl"


class SPEControlState(IntEnum):
  """The SPE state machine's states (`SPEControlStatesId`)."""

  UNINITIALIZED = 0
  INITIALIZING = 1
  READY = 2  # the working stack, without a collection plate, waits in the integration area
  FILTER_PLATE_PLACED = 3
  CLAMPING_FILTER_PLATE_1 = 4
  FILTER_PLATE_CLAMPED = 5
  PROCESS_FILTER_PLATE_TO_WASTE = 6
  RETRIEVING_FILTER_PLATE_1 = 7
  COLLECTION_PLATE_PLACED = 8
  RETRIEVING_FILTER_PLATE_2 = 9
  INTEGRATION_AREA_PLATE_STACK = 10
  PROCESS_FILTER_PLATE_TO_COLLECTION = 11
  CLAMPING_FILTER_PLATE_2 = 12
  EVAPORATOR_IN_INTEGRATION_AREA = 13
  EVAPORATOR_ENTERING_PROCESS_AREA = 14
  EVAPORATOR_IN_PROCESS_AREA = 15
  PRIMING_READY = 16
  PRIMING_FILTER_PLATE_PLACED = 17
  PRIMING_FILTER_PLATE_CLAMPED = 18
  PRIMING_COLLECTION_PLATE_PLACED = 19
  PRIMING_INTEGRATION_AREA_PLATE_STACK = 20
  DISPENSING_FILTER_PLATE_IN_DISPENSING_AREA = 21
  DISPENSING_COLLECTION_PLATE_IN_DISPENSING_AREA = 22
  COLLECTION_PLATE_IN_PROCESS_AREA = 23
  DISPENSING_INTEGRATION_AREA_PLATE_STACK_IN_DISPENSING_AREA = 24
  DISPENSING_FILTER_PLATE_PLACED = 25
  DISPENSING_COLLECTION_PLATE_PLACED = 26


class ControlPointType(IntEnum):
  """How a control point's value is read (`SPEControlPointType`)."""

  FLOW = 0  # standard litres per minute, per well
  PRESSURE = 1  # psig, per well
  NONE = 2  # idle: no pressure or flow for the duration


class WasteContainer(IntEnum):
  """`WasteContainerSelect`."""

  CONTAINER_1 = 0
  CONTAINER_2 = 1
  NONE = 2


@dataclass(frozen=True)
class ControlPoint:
  """One step of a process: a pressure or flow held for a time (`SPEControlPoint`)."""

  duration: float  # s
  type: ControlPointType
  value: float  # per well, in the type's units

  def encode_into(self, params: HoiParams) -> HoiParams:
    return params.add(self.duration, F32).add(int(self.type), WEnum).add(self.value, F32)


def parse_control_points(text: str, number_of_ports: int) -> List[ControlPoint]:
  """Control points from a Venus method's string, e.g. ``"pressure,20,240;pressure,65,60;"``.

  As Venus's driver does: whitespace is ignored, the last ``;`` is optional, the type is
  ``pressure``, ``flow`` or ``idle``, and each value is divided by the manifold's port count, since
  the string gives the whole manifold's value and the firmware takes a per-well one.

  Raises:
    ValueError: If the string is not a list of ``type,value,seconds;`` steps, or names an unknown
      type.
  """
  if number_of_ports <= 0:
    raise ValueError(f"number_of_ports must be positive, not {number_of_ports}")
  text = re.sub(r"\s+", "", text)
  if not text.endswith(";"):
    text += ";"
  if not re.fullmatch(r"([A-Za-z]+,\d*\.?\d*,\d*\.?\d*;)+", text):
    raise ValueError(f"control points are not 'type,value,seconds;' steps: {text!r}")
  types = {
    "pressure": ControlPointType.PRESSURE,
    "flow": ControlPointType.FLOW,
    "idle": ControlPointType.NONE,
  }
  points = []
  for n, step in enumerate(text.rstrip(";").split(";"), start=1):
    kind, value, duration = step.split(",")
    if kind.lower() not in types:
      raise ValueError(f"control point {n} has an unknown type {kind!r}")
    points.append(
      ControlPoint(float(duration), types[kind.lower()], float(value) / number_of_ports)
    )
  return points


# Status responses


@dataclass(frozen=True)
class LabwareParameters:
  filter_plate_height: F32
  filter_plate_nozzle_height: F32
  collection_plate_height: F32
  offset: F32
  maximum_penetration: F32


@dataclass(frozen=True)
class ControlPointRanges:
  min_flow_per_well: F32  # SLPM
  max_flow_per_well: F32
  min_pressure_per_well: F32  # psig
  max_pressure_per_well: F32


@dataclass(frozen=True)
class ManifoldInfo:
  serial_number: Str
  calibration_date: Str
  number_of_ports: U32


# Requests


@dataclass(frozen=True)
class MPE2Command(TCPCommand[None]):
  """A command to `SPEControl`. The device acknowledges it at once; poll `GetCompletionStatus`
  for the end of the motion or process it starts."""

  protocol: ClassVar[HamiltonProtocol] = HamiltonProtocol.OBJECT_DISCOVERY
  interface_id: ClassVar[int] = 1

  @classmethod
  def parse_response_parameters(cls, data: bytes) -> None:
    return None


@dataclass(frozen=True)
class Initialize(MPE2Command):
  """`Initialize(smart, vacuumTimeout, vacuumRunTime, wasteContainer, disableUpperLimitCheck)`.
  Venus's plain initialize sends this with smart, 10000 ms, 10000 ms and the first container
  present."""

  command_id: ClassVar[int] = 21
  smart: bool = True
  vacuum_timeout_ms: int = 10000
  vacuum_run_time_ms: int = 10000
  waste_container: WasteContainer = WasteContainer.CONTAINER_1
  disable_upper_limit_check: bool = False

  def build_parameters(self) -> HoiParams:
    return (
      HoiParams()
      .add(self.smart, PaddedBool)
      .add(self.vacuum_timeout_ms, U32)
      .add(self.vacuum_run_time_ms, U32)
      .add(int(self.waste_container), WEnum)
      .add(self.disable_upper_limit_check, PaddedBool)
    )


@dataclass(frozen=True)
class InitializeWithoutWaste(MPE2Command):
  """`Initialize(smart)`: what Venus sends when no waste container is present."""

  command_id: ClassVar[int] = 18
  smart: bool = True

  def build_parameters(self) -> HoiParams:
    return HoiParams().add(self.smart, PaddedBool)


@dataclass(frozen=True)
class FilterPlatePlaced(MPE2Command):
  command_id: ClassVar[int] = 7
  filter_height: float = 0.0  # mm
  nozzle_height: float = 0.0  # mm

  def build_parameters(self) -> HoiParams:
    return HoiParams().add(self.filter_height, F32).add(self.nozzle_height, F32)


@dataclass(frozen=True)
class FilterPlateRemoved(MPE2Command):
  command_id: ClassVar[int] = 8


@dataclass(frozen=True)
class ClampFilterPlate(MPE2Command):
  command_id: ClassVar[int] = 9


@dataclass(frozen=True)
class RetrieveFilterPlate(MPE2Command):
  command_id: ClassVar[int] = 10


@dataclass(frozen=True)
class CollectionPlatePlaced(MPE2Command):
  command_id: ClassVar[int] = 11
  collection_plate_height: float = 0.0  # mm
  offset_from_nozzles: float = 0.0  # mm

  def build_parameters(self) -> HoiParams:
    return HoiParams().add(self.collection_plate_height, F32).add(self.offset_from_nozzles, F32)


@dataclass(frozen=True)
class CollectionPlateRemoved(MPE2Command):
  command_id: ClassVar[int] = 12


@dataclass(frozen=True)
class ProcessFilterPlateToWaste(MPE2Command):
  """`ProcessFilterPlateToWaste(controlPoints, returnFilterPlateToIntegrationArea, wasteContainer,
  disableUpperLimitCheck)`, the overload Venus sends."""

  command_id: ClassVar[int] = 23
  control_points: Sequence[ControlPoint] = ()
  return_filter_plate_to_integration_area: bool = True
  waste_container: WasteContainer = WasteContainer.CONTAINER_1
  disable_upper_limit_check: bool = False

  def build_parameters(self) -> HoiParams:
    return (
      HoiParams()
      .add(list(self.control_points), StructArray())
      .add(self.return_filter_plate_to_integration_area, PaddedBool)
      .add(int(self.waste_container), WEnum)
      .add(self.disable_upper_limit_check, PaddedBool)
    )


@dataclass(frozen=True)
class ProcessFilterPlateToCollection(MPE2Command):
  command_id: ClassVar[int] = 14
  control_points: Sequence[ControlPoint] = ()
  return_filter_plate_to_integration_area: bool = True

  def build_parameters(self) -> HoiParams:
    return (
      HoiParams()
      .add(list(self.control_points), StructArray())
      .add(self.return_filter_plate_to_integration_area, PaddedBool)
    )


@dataclass(frozen=True)
class Abort(MPE2Command):
  command_id: ClassVar[int] = 15


@dataclass(frozen=True)
class MPE2StatusRequest(MPE2Command):
  action_code: ClassVar[int] = Hoi2Action.STATUS_REQUEST


@dataclass(frozen=True)
class GetControlState(MPE2StatusRequest):
  command_id: ClassVar[int] = 1

  @dataclass(frozen=True)
  class Response:
    value: WEnum

  @classmethod
  def parse_response_parameters(cls, data: bytes) -> SPEControlState:  # type: ignore[override]
    return SPEControlState(parse_into_struct(HoiParamsParser(data), cls.Response).value)


@dataclass(frozen=True)
class GetLabwareParameters(MPE2StatusRequest):
  command_id: ClassVar[int] = 2

  @classmethod
  def parse_response_parameters(cls, data: bytes) -> LabwareParameters:  # type: ignore[override]
    return parse_into_struct(HoiParamsParser(_struct_payload(data)), LabwareParameters)


@dataclass(frozen=True)
class GetControlPointRanges(MPE2StatusRequest):
  command_id: ClassVar[int] = 4

  @classmethod
  def parse_response_parameters(cls, data: bytes) -> ControlPointRanges:  # type: ignore[override]
    return parse_into_struct(HoiParamsParser(_struct_payload(data)), ControlPointRanges)


@dataclass(frozen=True)
class GetManifoldInformation(MPE2StatusRequest):
  command_id: ClassVar[int] = 5

  @classmethod
  def parse_response_parameters(cls, data: bytes) -> ManifoldInfo:  # type: ignore[override]
    return parse_into_struct(HoiParamsParser(_struct_payload(data)), ManifoldInfo)


@dataclass(frozen=True)
class GetIsInitialized(MPE2StatusRequest):
  command_id: ClassVar[int] = 17

  @dataclass(frozen=True)
  class Response:
    value: PaddedBool

  @classmethod
  def parse_response_parameters(cls, data: bytes) -> bool:  # type: ignore[override]
    return bool(parse_into_struct(HoiParamsParser(data), cls.Response).value)


@dataclass(frozen=True)
class GetCompletionStatus(MPE2StatusRequest):
  """True once the last command has finished; the device reports that command's errors with it."""

  command_id: ClassVar[int] = 19

  @dataclass(frozen=True)
  class Response:
    value: PaddedBool

  @classmethod
  def parse_response_parameters(cls, data: bytes) -> bool:  # type: ignore[override]
    return bool(parse_into_struct(HoiParamsParser(data), cls.Response).value)


def _struct_payload(data: bytes) -> bytes:
  """The fields of a status that returns one structure, unwrapped from its STRUCTURE fragment."""
  _, payload = HoiParamsParser(data).parse_next()
  return cast(bytes, payload)
