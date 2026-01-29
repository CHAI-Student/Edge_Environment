from aiomqtt.types import PayloadType
from pydantic import BaseModel
from pydantic_core import ValidationError

from core import core
from config import settings

from .protocol import *


IF_ID = "IF_02"
IF_SYSID = "e31e840a-7137-4ec8-8f86-14d2607d836b"
IF_HOST = "CRKPNTCHAI"
IF_DATE = "20240801173908"

HEADER = {
    "IF_ID": IF_ID,
    "IF_SYSID": IF_SYSID,
    "IF_HOST": IF_HOST,
    "IF_DATE": IF_DATE,
}


class MonitorReqData(ReqData):
    camera_status: str
    deadbolt_status: str
    loadcell_status: str
    card_terminal_status: str


class MonitorReqMessage(BaseModel):
    HEADER: Header
    DATA: MonitorReqData


@core.scheduler.register(
    publish_topic="chai/device/{DEVICE_ID}/health",
    interval=30.0,
)
async def monitor_handler():
    camera_status = "OK"  # TODO: check actual status
    deadbolt_status = "OK"
    loadcell_status = "OK"
    card_terminal_status = "OK"

    return MonitorReqMessage.model_validate(
        {
            "HEADER": HEADER,
            "DATA": {
                "division_idx": settings.division_idx,
                "device_idx": settings.device_idx,
                "camera_status": camera_status,
                "deadbolt_status": deadbolt_status,
                "loadcell_status": loadcell_status,
                "card_terminal_status": card_terminal_status,
            },
        }
    ).model_dump_json()
