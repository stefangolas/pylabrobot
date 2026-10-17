"""Drivers for the MPE²: one over HOI/TCP, and a simulation that walks the same state machine."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, List, Optional, Sequence, Set, Union, cast

from pylabrobot.hamilton.mpe2.commands import (
  SPE_CONTROL_PATH,
  Abort,
  ClampFilterPlate,
  CollectionPlatePlaced,
  CollectionPlateRemoved,
  ControlPoint,
  ControlPointRanges,
  ControlPointType,
  FilterPlatePlaced,
  FilterPlateRemoved,
  GetCompletionStatus,
  GetControlPointRanges,
  GetControlState,
  GetIsInitialized,
  GetLabwareParameters,
  GetManifoldInformation,
  Initialize,
  LabwareParameters,
  ManifoldInfo,
  MPE2Command,
  ProcessFilterPlateToCollection,
  ProcessFilterPlateToWaste,
  RetrieveFilterPlate,
  SPEControlState,
  WasteContainer,
  parse_control_points,
)
from pylabrobot.hamilton.transport.tcp.packets import Address
from pylabrobot.hamilton.transport.tcp.tcp import HamiltonTCPClient

logger = logging.getLogger(__name__)

ControlPoints = Union[str, Sequence[ControlPoint]]
S = SPEControlState


class MPE2Error(RuntimeError):
  """A command the MPE² refused or failed."""


class MPE2Driver:
  """Speaks to one MPE² over HOI/TCP.

  Every command returns once the device reports it complete: the device acknowledges a command at
  once, and the driver then polls `CompletionStatus` (the device reports the command's errors
  there, which the transport raises).

  Serial-connected units (an FTDI COM port, as at NIST) frame HOI differently and are not covered
  yet; see venus-interop `docs/notes/MPE2.md` §2.
  """

  def __init__(
    self,
    host: str,
    port: int,
    poll_interval: float = 0.25,
    command_timeout: float = 3600.0,
    client: Optional[HamiltonTCPClient] = None,
  ):
    """
    Args:
      host, port: where the MPE² listens.
      poll_interval: seconds between completion checks.
      command_timeout: the longest a command may take, in seconds; a process lasts as long as its
        control points add up to, plus its motions.
      client: a HOI client to use instead of one built from host and port.
    """
    self.client = client if client is not None else HamiltonTCPClient(host=host, port=port)
    self.poll_interval = poll_interval
    self.command_timeout = command_timeout
    self._spe: Optional[Address] = None
    self.number_of_ports: int = 0

  async def setup(self) -> None:
    await self.client.setup()
    self._spe = await self.client.resolve_path(SPE_CONTROL_PATH)
    self.number_of_ports = (await self.request_manifold_information()).number_of_ports

  async def stop(self) -> None:
    await self.client.stop()
    self._spe = None

  # The two primitives a simulation replaces

  def _dest(self) -> Address:
    if self._spe is None:
      raise RuntimeError("MPE2Driver is not set up")
    return self._spe

  async def _run(self, command_type: type, **params) -> None:
    """Send a command and wait for the device to finish it."""
    await self.client.execute(command_type(dest=self._dest(), **params))
    deadline = time.monotonic() + self.command_timeout
    while not await self._query(GetCompletionStatus):
      if time.monotonic() > deadline:
        raise MPE2Error(f"{command_type.__name__} did not complete in {self.command_timeout} s")
      await asyncio.sleep(self.poll_interval)

  async def _query(self, command_type: type) -> Any:
    return await self.client.execute(command_type(dest=self._dest()))

  # Commands

  async def initialize(
    self,
    waste_container: WasteContainer = WasteContainer.CONTAINER_1,
    smart: bool = True,
    vacuum_timeout_ms: int = 10000,
    vacuum_run_time_ms: int = 10000,
    disable_upper_limit_check: bool = False,
  ) -> None:
    await self._run(
      Initialize,
      smart=smart,
      vacuum_timeout_ms=vacuum_timeout_ms,
      vacuum_run_time_ms=vacuum_run_time_ms,
      waste_container=waste_container,
      disable_upper_limit_check=disable_upper_limit_check,
    )

  async def filter_plate_placed(self, filter_height: float, nozzle_height: float) -> None:
    """Tell the MPE² a filter plate now stands on the working stack (heights in mm)."""
    await self._run(FilterPlatePlaced, filter_height=filter_height, nozzle_height=nozzle_height)

  async def filter_plate_removed(self) -> None:
    await self._run(FilterPlateRemoved)

  async def clamp_filter_plate(self) -> None:
    await self._run(ClampFilterPlate)

  async def retrieve_filter_plate(self) -> None:
    await self._run(RetrieveFilterPlate)

  async def collection_plate_placed(
    self, collection_plate_height: float, offset_from_nozzles: float
  ) -> None:
    await self._run(
      CollectionPlatePlaced,
      collection_plate_height=collection_plate_height,
      offset_from_nozzles=offset_from_nozzles,
    )

  async def collection_plate_removed(self) -> None:
    await self._run(CollectionPlateRemoved)

  async def process_filter_plate_to_waste(
    self,
    control_points: ControlPoints,
    return_filter_plate_to_integration_area: bool = True,
    waste_container: WasteContainer = WasteContainer.CONTAINER_1,
    disable_upper_limit_check: bool = False,
  ) -> None:
    """Press the filter plate's contents to waste.

    Args:
      control_points: per-well control points, or a Venus method's string (whose values are for the
        whole manifold; see `parse_control_points`).
    """
    await self._run(
      ProcessFilterPlateToWaste,
      control_points=tuple(self._points(control_points)),
      return_filter_plate_to_integration_area=return_filter_plate_to_integration_area,
      waste_container=waste_container,
      disable_upper_limit_check=disable_upper_limit_check,
    )

  async def process_filter_plate_to_collection(
    self,
    control_points: ControlPoints,
    return_filter_plate_to_integration_area: bool = True,
  ) -> None:
    """Press the filter plate's contents into the collection plate under it."""
    await self._run(
      ProcessFilterPlateToCollection,
      control_points=tuple(self._points(control_points)),
      return_filter_plate_to_integration_area=return_filter_plate_to_integration_area,
    )

  async def abort(self) -> None:
    await self.client.execute(Abort(dest=self._dest()))

  # Status

  async def request_control_state(self) -> SPEControlState:
    return cast(SPEControlState, await self._query(GetControlState))

  async def request_is_initialized(self) -> bool:
    return cast(bool, await self._query(GetIsInitialized))

  async def request_labware_parameters(self) -> LabwareParameters:
    return cast(LabwareParameters, await self._query(GetLabwareParameters))

  async def request_control_point_ranges(self) -> ControlPointRanges:
    return cast(ControlPointRanges, await self._query(GetControlPointRanges))

  async def request_manifold_information(self) -> ManifoldInfo:
    return cast(ManifoldInfo, await self._query(GetManifoldInformation))

  def _points(self, control_points: ControlPoints) -> List[ControlPoint]:
    if isinstance(control_points, str):
      return parse_control_points(control_points, self.number_of_ports)
    return list(control_points)


# The state machine, as the instrument definition describes it. Transitory states are listed in the
# order a command passes through them; the ones in brackets in venus-interop docs/notes/MPE2.md §4
# are inferred from the definition's help strings and not yet confirmed on hardware.


class MPE2SimulationDriver(MPE2Driver):
  """An MPE² that answers like the real one, from the state machine alone.

  Commands are accepted only in the states the device accepts them in (otherwise `MPE2Error`, as the
  device's InvalidCommandForState). Each command passes through its transitory states; observers
  added with `add_state_observer` see every state, which is what an animation follows. With
  `time_scale` 0 (the default) nothing waits; 1 waits as long as the device would.
  """

  MOTION_TIME = 5.0  # s per clamp, retrieve or return; a guess, not measured

  def __init__(
    self,
    number_of_ports: int = 96,
    time_scale: float = 0.0,
    control_point_ranges: Optional[ControlPointRanges] = None,
  ):
    self.client = None  # type: ignore[assignment]
    self.poll_interval = 0.0
    self.command_timeout = float("inf")
    self._spe = None
    self.number_of_ports = number_of_ports
    self.time_scale = time_scale
    # Ranges are the device's calibration; these only bound obvious mistakes.
    self.control_point_ranges = control_point_ranges or ControlPointRanges(
      min_flow_per_well=0.0,
      max_flow_per_well=10.0,
      min_pressure_per_well=0.0,
      max_pressure_per_well=100.0,
    )
    self.state = S.UNINITIALIZED
    self.collection_plate = False
    self.filter_plate = False
    self.clamped = False
    self.labware = LabwareParameters(0.0, 0.0, 0.0, 0.0, 0.0)
    self.traversed: List[SPEControlState] = []
    self.processed: List[tuple] = []  # (destination, control points), for tests and bookkeeping
    self._observers: List[Callable[[SPEControlState], None]] = []

  def add_state_observer(self, observer: Callable[[SPEControlState], None]) -> None:
    self._observers.append(observer)

  async def setup(self) -> None:
    pass

  async def stop(self) -> None:
    pass

  async def _go(self, *states: SPEControlState, seconds: float = 0.0) -> None:
    for state in states:
      self.state = state
      self.traversed.append(state)
      for observer in self._observers:
        observer(state)
    if seconds and self.time_scale:
      await asyncio.sleep(seconds * self.time_scale)

  def _require(self, allowed: Set[SPEControlState], command: str) -> None:
    if self.state not in allowed:
      raise MPE2Error(f"{command}: invalid command for state {self.state.name}")

  def _check_points(self, points: Sequence[ControlPoint]) -> float:
    r = self.control_point_ranges
    for n, p in enumerate(points, start=1):
      if (
        p.type == ControlPointType.PRESSURE
        and not r.min_pressure_per_well <= p.value <= r.max_pressure_per_well
      ):
        raise MPE2Error(f"control point {n}: pressure {p.value} per well is out of range")
      if (
        p.type == ControlPointType.FLOW
        and not r.min_flow_per_well <= p.value <= r.max_flow_per_well
      ):
        raise MPE2Error(f"control point {n}: flow {p.value} per well is out of range")
    return sum(p.duration for p in points)

  async def _run(self, command_type: type, **params) -> None:
    self.traversed = []
    name = command_type.__name__
    if command_type is Initialize:
      self.collection_plate = self.filter_plate = self.clamped = False
      await self._go(S.INITIALIZING, seconds=self.MOTION_TIME)
      await self._go(S.READY)
    elif command_type is FilterPlatePlaced:
      self._require({S.READY, S.COLLECTION_PLATE_PLACED}, name)
      self.filter_plate = True
      self.labware = LabwareParameters(
        params["filter_height"],
        params["nozzle_height"],
        self.labware.collection_plate_height,
        self.labware.offset,
        self.labware.maximum_penetration,
      )
      await self._go(
        S.INTEGRATION_AREA_PLATE_STACK if self.collection_plate else S.FILTER_PLATE_PLACED
      )
    elif command_type is CollectionPlatePlaced:
      # Also with the filter plate clamped: the integration area is then free, and the NIST DNA
      # Extraction's elution places the collection plate there after clamping.
      self._require({S.READY, S.FILTER_PLATE_CLAMPED}, name)
      self.collection_plate = True
      self.labware = LabwareParameters(
        self.labware.filter_plate_height,
        self.labware.filter_plate_nozzle_height,
        params["collection_plate_height"],
        params["offset_from_nozzles"],
        self.labware.maximum_penetration,
      )
      await self._go(S.FILTER_PLATE_CLAMPED if self.clamped else S.COLLECTION_PLATE_PLACED)
    elif command_type is ClampFilterPlate:
      self._require({S.FILTER_PLATE_PLACED, S.INTEGRATION_AREA_PLATE_STACK}, name)
      self.clamped = True
      clamping = S.CLAMPING_FILTER_PLATE_2 if self.collection_plate else S.CLAMPING_FILTER_PLATE_1
      await self._go(clamping, seconds=self.MOTION_TIME)
      await self._go(S.FILTER_PLATE_CLAMPED)
    elif command_type is RetrieveFilterPlate:
      self._require({S.FILTER_PLATE_CLAMPED}, name)
      await self._retrieve()
    elif command_type is ProcessFilterPlateToWaste:
      self._require({S.FILTER_PLATE_PLACED, S.FILTER_PLATE_CLAMPED}, name)
      if self.collection_plate:
        raise MPE2Error(f"{name}: a collection plate is in the way of the waste tray")
      seconds = self._check_points(params["control_points"])
      if not self.clamped:
        await self._go(S.CLAMPING_FILTER_PLATE_1, seconds=self.MOTION_TIME)
        self.clamped = True
      await self._go(S.PROCESS_FILTER_PLATE_TO_WASTE, seconds=seconds)
      self.processed.append(("waste", tuple(params["control_points"])))
      if params["return_filter_plate_to_integration_area"]:
        await self._retrieve()
      else:
        await self._go(S.FILTER_PLATE_CLAMPED)
    elif command_type is ProcessFilterPlateToCollection:
      self._require({S.INTEGRATION_AREA_PLATE_STACK, S.FILTER_PLATE_CLAMPED}, name)
      if not self.collection_plate:
        raise MPE2Error(f"{name}: no collection plate")
      seconds = self._check_points(params["control_points"])
      if not self.clamped:
        await self._go(S.CLAMPING_FILTER_PLATE_2, seconds=self.MOTION_TIME)
        self.clamped = True
      await self._go(S.PROCESS_FILTER_PLATE_TO_COLLECTION, seconds=seconds)
      self.processed.append(("collection", tuple(params["control_points"])))
      if params["return_filter_plate_to_integration_area"]:
        await self._retrieve()
      else:
        await self._go(S.FILTER_PLATE_CLAMPED)
    elif command_type is FilterPlateRemoved:
      self._require({S.FILTER_PLATE_PLACED, S.INTEGRATION_AREA_PLATE_STACK}, name)
      self.filter_plate = False
      await self._go(S.COLLECTION_PLATE_PLACED if self.collection_plate else S.READY)
    elif command_type is CollectionPlateRemoved:
      self._require({S.COLLECTION_PLATE_PLACED, S.FILTER_PLATE_CLAMPED}, name)
      if not self.collection_plate:
        raise MPE2Error(f"{name}: no collection plate")
      self.collection_plate = False
      await self._go(S.FILTER_PLATE_CLAMPED if self.clamped else S.READY)
    else:
      raise NotImplementedError(f"the simulation does not model {name}")

  async def _retrieve(self) -> None:
    self.clamped = False
    if self.collection_plate:
      await self._go(S.RETRIEVING_FILTER_PLATE_2, seconds=self.MOTION_TIME)
      await self._go(S.INTEGRATION_AREA_PLATE_STACK)
    else:
      await self._go(S.RETRIEVING_FILTER_PLATE_1, seconds=self.MOTION_TIME)
      await self._go(S.FILTER_PLATE_PLACED)

  async def _query(self, command_type: type) -> Any:
    if command_type is GetControlState:
      return self.state
    if command_type is GetIsInitialized:
      return self.state != S.UNINITIALIZED
    if command_type is GetCompletionStatus:
      return True
    if command_type is GetLabwareParameters:
      return self.labware
    if command_type is GetControlPointRanges:
      return self.control_point_ranges
    if command_type is GetManifoldInformation:
      return ManifoldInfo("SIMULATED", "", self.number_of_ports)
    raise NotImplementedError(f"the simulation does not answer {command_type.__name__}")

  async def abort(self) -> None:
    pass


__all__ = ["MPE2Driver", "MPE2SimulationDriver", "MPE2Error", "MPE2Command"]
