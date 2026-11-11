"""Constants shared by the io_manager classes."""

import os
from typing import Any


Record = dict[str, Any]
Records = list[Record]
AiAudit = dict[str, Any]

IS_WINDOWS = os.name == "nt"
