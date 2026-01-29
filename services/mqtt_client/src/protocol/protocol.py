from typing import Dict, Any, Literal, Union
from pydantic import BaseModel, ConfigDict

__all__ = ["Header", "ReqData", "AckData", "ReqMessage", "AckMessage", "Message"]


class Header(BaseModel):
    IF_ID: str
    IF_SYSID: str
    IF_HOST: str
    IF_DATE: Union[int, str]  # Unix timestamp (Node.js) or string format


class ReqData(BaseModel):
    division_idx: str
    device_idx: str
    model_config = ConfigDict(extra="allow")


class AckData(BaseModel):
    division_idx: str
    device_idx: str
    result_cd: Literal["S", "F"]
    result_msg: str
    model_config = ConfigDict(extra="allow")


class ReqMessage(BaseModel):
    HEADER: Header
    DATA: ReqData


class AckMessage(BaseModel):
    HEADER: Header
    DATA: AckData


class Message(BaseModel):
    HEADER: Header
    DATA: Dict[str, Any]
