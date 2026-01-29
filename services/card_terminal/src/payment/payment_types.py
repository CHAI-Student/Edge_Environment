from typing import TypedDict, Optional

from .const import CardInfoData, StatusCode, ResponseCode

class TxTokenData(TypedDict):
    status: StatusCode
    vankey_hash: Optional[str]
    card_info: Optional[CardInfoData]
    response_code: ResponseCode
    message: str

class TxTokenApprovalData(TypedDict):
    status: StatusCode
    authorization_number: Optional[str]
    card_info: Optional[CardInfoData]
    vankey: Optional[str]
    response_code: ResponseCode
    message: str

class TxTokenCancelData(TypedDict):
    status: StatusCode
    card_info: Optional[CardInfoData]
    vankey: Optional[str]
    response_code: ResponseCode
    message: str

class TxSPayApprovalData(TypedDict):
    status: StatusCode
    authorization_number: Optional[str]
    card_info: Optional[CardInfoData]
    vankey: Optional[str]
    response_code: ResponseCode
    message: str

class TxSPayCancelData(TypedDict):
    status: StatusCode
    card_info: Optional[CardInfoData]
    vankey: Optional[str]
    response_code: ResponseCode
    message: str

class DeviceCheckData(TypedDict):
    response_code: ResponseCode
