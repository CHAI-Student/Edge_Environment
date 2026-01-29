"""
Re-export config from core.config for backward compatibility.

All modules using `from ..config import ...` will work with this re-export.
"""

from core.config import Settings, settings

__all__ = ["Settings", "settings"]
