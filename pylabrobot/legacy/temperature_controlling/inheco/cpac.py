from pylabrobot.legacy.temperature_controlling.inheco.control_box import InhecoTECControlBox
from pylabrobot.legacy.temperature_controlling.inheco.cpac_backend import InhecoCPACBackend
from pylabrobot.legacy.temperature_controlling.temperature_controller import TemperatureController
from pylabrobot.resources.coordinate import Coordinate


def inheco_cpac_ultraflat(
  name: str, control_box: InhecoTECControlBox, index: int
) -> TemperatureController:
  """Inheco CPAC Ultraflat
  7000166, 7000190, 7000165

  https://www.inheco.com/data/pdf/cpac-brochure-1013-1032-34.pdf
  """

  return TemperatureController(
    name=name,
    backend=InhecoCPACBackend(control_box=control_box, index=index),
    # Inheco's drawing: 129 long, 89 wide (thermal adapter), 80 to the adapter's top. A plate
    # stands centred, its bottom 77 up (measured, flat adapter). See `pylabrobot.inheco.cpac`.
    size_x=129,
    size_y=89,
    size_z=80,
    child_location=Coordinate(x=(129 - 127.76) / 2, y=(89 - 85.48) / 2, z=77),
    model=inheco_cpac_ultraflat.__name__,
  )
