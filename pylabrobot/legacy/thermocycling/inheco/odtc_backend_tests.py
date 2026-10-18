import unittest
import xml.etree.ElementTree as ET
from unittest.mock import AsyncMock

from pylabrobot.legacy.thermocycling.inheco.odtc_backend import ExperimentalODTCBackend
from pylabrobot.legacy.thermocycling.standard import Protocol, Stage, Step


class ODTCMethodSetTests(unittest.IsolatedAsyncioTestCase):
  def setUp(self):
    self.backend = ExperimentalODTCBackend(ip="127.0.0.1", client_ip="127.0.0.1")
    self.backend._sila_interface.send_command = AsyncMock()  # type: ignore[method-assign]
    self.send = self.backend._sila_interface.send_command

  async def test_upload_method_set_sends_the_document_as_methods_xml(self):
    doc = '<?xml version="1.0" encoding="utf-8"?><MethodSet><Method methodName="m"/></MethodSet>'
    await self.backend.upload_method_set(doc)
    command, kwargs = self.send.call_args.args[0], self.send.call_args.kwargs
    self.assertEqual(command, "SetParameters")
    param = ET.fromstring(kwargs["paramsXML"]).find("Parameter")
    self.assertEqual(param.get("name"), "MethodsXML")
    self.assertEqual(param.find("String").text, doc)

  async def test_execute_method_by_name_with_and_without_priority(self):
    await self.backend.execute_method("Roche_AVENIO_CGP_Init", priority=10000)
    self.send.assert_awaited_with("ExecuteMethod", methodName="Roche_AVENIO_CGP_Init", priority=10000)
    await self.backend.execute_method("Dehumidify block")
    self.send.assert_awaited_with("ExecuteMethod", methodName="Dehumidify block")

  async def test_run_protocol_uploads_then_executes(self):
    protocol = Protocol(stages=[Stage(steps=[Step(temperature=[95.0], hold_seconds=30)], repeats=1)])
    await self.backend.run_protocol(protocol, method_name="p")
    self.assertEqual([c.args[0] for c in self.send.call_args_list], ["SetParameters", "ExecuteMethod"])
    self.assertEqual(self.send.call_args_list[1].kwargs, {"methodName": "p"})
