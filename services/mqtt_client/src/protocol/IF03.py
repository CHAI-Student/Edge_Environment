from typing import Literal

from aiomqtt.types import PayloadType
from pydantic import BaseModel
from pydantic_core import ValidationError

from core import core
from config import settings

from .protocol import *


IF_ID = "IF_03"
IF_SYSID = "45BDA-12A3DASD-1231-1E12-3123D3DAZ23"
IF_HOST = "CRKPNTCHAI"
IF_DATE = "20240503152229"

HEADER = {
    "IF_ID": IF_ID,
    "IF_SYSID": IF_SYSID,
    "IF_HOST": IF_HOST,
    "IF_DATE": IF_DATE,
}


class ManualDoorReqData(ReqData):
    door_action: Literal["OPEN", "CLOSE"]


class ManualDoorReqMessage(BaseModel):
    HEADER: Header
    DATA: ManualDoorReqData


class ManualDoorAckData(AckData):
    door_status: Literal["OPEN", "CLOSE"]


class ManualDoorAckMessage(BaseModel):
    HEADER: Header
    DATA: ManualDoorAckData


@core.router.register(
    subscribe_topic="chai/device/{DEVICE_ID}/cmd/door/manual",
    publish_topic="chai/device/{DEVICE_ID}/ack/door/manual",
)
async def manual_door_handler(payload: PayloadType):
    if not isinstance(payload, (str, bytes, bytearray)):
        return None

    try:
        req_message = ManualDoorReqMessage.model_validate_json(payload)
    except ValidationError as e:
        return None

    # TODO: Implement door control logic
    # Call deadbolt_driver service to open/close door
    door_action = req_message.DATA.door_action

    return ManualDoorAckMessage.model_validate(
        {
            "HEADER": HEADER,
            "DATA": {
                "division_idx": settings.division_idx,
                "device_idx": settings.device_idx,
                "result_cd": "S",
                "result_msg": f"door {door_action.lower()} success",
                "door_status": door_action,
            },
        }
    ).model_dump_json()
