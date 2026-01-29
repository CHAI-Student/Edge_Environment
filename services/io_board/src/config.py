"""
Re-export config from core.config for backward compatibility.

All modules using `from config import ...` will work with this re-export.
"""

from core.config import (
    Settings,
    SerialModel,
    APIModel,
    PollingModel,
)

__all__ = [
    "Settings",
    "SerialModel",
    "APIModel",
    "PollingModel",
]
