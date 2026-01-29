import time
import uuid
from typing import Literal

from aiomqtt.types import PayloadType
from pydantic import BaseModel
from pydantic_core import ValidationError

from core import core
from config import settings

from .protocol import *


IF_ID = "IF_04"
IF_HOST = "CHAI"  # Match Node.js ManualDoor.js IF_HOST


def make_header(if_sysid: str | None = None) -> dict:
    """Create dynamic header matching Node.js format.

    Node.js uses:
    - IF_SYSID: uuid or echo from request
    - IF_DATE: Unix timestamp (milliseconds)
    """
    return {
        "IF_ID": IF_ID,
        "IF_SYSID": if_sysid or str(uuid.uuid4()),
        "IF_HOST": IF_HOST,
        "IF_DATE": int(time.time() * 1000),  # Unix timestamp in ms like Node.js Date.now()
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
    qos=1,  # Match Node.js QoS for door control
)
async def collect_door_handler(payload: PayloadType):
    if not isinstance(payload, (str, bytes, bytearray)):
        return None

    try:
        req_message = CollectDoorReqMessage.model_validate_json(payload)
    except ValidationError as e:
        return None

    # Echo IF_SYSID from request (like Node.js ManualDoor.js)
    if_sysid = req_message.HEADER.IF_SYSID
    door_state = req_message.DATA.door_state

    # TODO: Implement actual collect door logic via io_board API

    return CollectDoorAckMessage.model_validate(
        {
            "HEADER": make_header(if_sysid),  # Dynamic header with echoed IF_SYSID
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
