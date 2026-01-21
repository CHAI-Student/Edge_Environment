from typing import Literal

from aiomqtt.types import PayloadType
from pydantic import BaseModel
from pydantic_core import ValidationError

from ..core import core
from ..config import settings

from .protocol import *


IF_ID = "IF_04"
IF_SYSID = "45BDA-12A3DASD-1231-1E12-3123D3DAZ23"
IF_HOST = "CRKPNTCHAI"
IF_DATE = "20240503152229"

HEADER = {
    "IF_ID": IF_ID,
    "IF_SYSID": IF_SYSID,
    "IF_HOST": IF_HOST,
    "IF_DATE": IF_DATE,
}


class CollectDoorReqData(ReqData):
    door_state: Literal["OPEN", "CLOSE"]


class CollectDoorReqMessage(BaseModel):
    HEADER: Header
    DATA: CollectDoorReqData


class CollectDoorAckData(AckData):
    door_state: Literal["OPEN", "CLOSE"]
    camera_status: str
    deadbolt_status: str
    loadcell_status: str


class CollectDoorAckMessage(BaseModel):
    HEADER: Header
    DATA: CollectDoorAckData


@core.router.register(
    subscribe_topic="chai/device/{DEVICE_ID}/cmd/door/collect",
    publish_topic="chai/device/{DEVICE_ID}/ack/door/collect",
)
async def collect_door_handler(payload: PayloadType):
    if not isinstance(payload, (str, bytes, bytearray)):
        return None

    try:
        req_message = CollectDoorReqMessage.model_validate_json(payload)
    except ValidationError as e:
        return None

    # TODO: Implement collect door logic
    door_state = req_message.DATA.door_state

    return CollectDoorAckMessage.model_validate(
        {
            "HEADER": HEADER,
            "DATA": {
                "division_idx": settings.division_idx,
                "device_idx": settings.device_idx,
                "result_cd": "S",
                "result_msg": f"collect door {door_state.lower()} success",
                "door_state": door_state,
                "camera_status": "OK",
                "deadbolt_status": "OK",
                "loadcell_status": "OK",
            },
        }
    ).model_dump_json()
