"""
Model Service - AI Smart Vending Machine Product Judgment.

Real-time product recognition via:
- SSE subscription to io_board (loadcell.change events)
- Camera driver integration (Top + Zone cameras)
- YOLOv8 inference with hand-proximity filtering
- Weight-based count validation
- Node.js result delivery
"""

__version__ = "1.0.0"
