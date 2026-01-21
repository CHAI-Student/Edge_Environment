"""
API module for Model service.

REST API 엔드포인트 및 Node.js 통신.
"""

from .routes import router
from .node_client import NodeJSClient

__all__ = [
    "router",
    "NodeJSClient",
]
