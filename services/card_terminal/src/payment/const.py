from enum import Enum as PyEnum
from typing import Optional, TypedDict

from construct import Byte, Bytes, Mapping

class ServiceCode(str, PyEnum):
    # TOKEN
    TX_TOKEN_INIT = "PS"
    TX_TOKEN_GENERATE = "TQ"
    TX_TOKEN_APPROVE = "D8"
    TX_TOKEN_CANCEL = "D9"
    # SAMSUNG WALLET
    TX_SPAY_INIT = "PA"
    TX_SPAY_APPROVE = "D1"
    TX_SPAY_CANCEL = "D7"
    # RFID
    TX_RFID_INIT = "PR"
    # MISC
    AGE_CHECK = "AC"
    DEVICE_CHECK = "PC"

class MessageType(bytes, PyEnum):
    REQUEST = b"10"
    RESPONSE = b"20"

class StatusCode(int, PyEnum):
    Y = 0x59  # 'Y'
    N = 0x4E  # 'N'

class AuthorizationType(int, PyEnum):
    PRE_AUTH = 0x00
    PURCHASE = 0x01

class ResponseCode(int, PyEnum):
    SUCCESS             = 0x00
    TIMEOUT             = 0xB0
    CANCEL              = 0xB1
    CONDITION_FAIL      = 0xB2
    FORMAT_ERROR        = 0xB3
    SERVICE_UNAVAILABLE = 0xB4
    ERROR_RF            = 0xB5
    ERROR_VAN           = 0xB6
    ERROR_POS           = 0xC0
    NETWORK_ERROR       = 0xC1
    ERROR               = 0xFF

class CardInfoData(TypedDict):
    SERIAL_NUMBER: str
    ACQUIRER_ID: str
    ACQUIRER_NAME: str
    ISSUER_ID: str
    ISSUER_NAME: str
    MERCHANT_ID: str

def build_card_info_data(card_info) -> Optional[CardInfoData]:
    if card_info is None:
        return None
    if isinstance(card_info, str):
        return None
    return CardInfoData(
        SERIAL_NUMBER=card_info.serial_number,
        ACQUIRER_ID=card_info.acquirer_id,
        ACQUIRER_NAME=card_info.acquirer_name,
        ISSUER_ID=card_info.issuer_id,
        ISSUER_NAME=card_info.issuer_name,
        MERCHANT_ID=card_info.merchant_id,
    )

STX = b"\x02"
ETX = b"\x03"

FS = b"\x1C"
RS = b"\x1E"

Construct_MessageType = Mapping(
    Bytes(2),
    {
        MessageType.REQUEST: MessageType.REQUEST.value,
        MessageType.RESPONSE: MessageType.RESPONSE.value,
    }
)

Construct_ResponseCode = Mapping(
    Byte,
    {
        ResponseCode.SUCCESS: ResponseCode.SUCCESS.value,
        ResponseCode.TIMEOUT: ResponseCode.TIMEOUT.value,
        ResponseCode.CANCEL: ResponseCode.CANCEL.value,
        ResponseCode.CONDITION_FAIL: ResponseCode.CONDITION_FAIL.value,
        ResponseCode.FORMAT_ERROR: ResponseCode.FORMAT_ERROR.value,
        ResponseCode.SERVICE_UNAVAILABLE: ResponseCode.SERVICE_UNAVAILABLE.value,
        ResponseCode.ERROR_RF: ResponseCode.ERROR_RF.value,
        ResponseCode.ERROR_VAN: ResponseCode.ERROR_VAN.value,
        ResponseCode.ERROR_POS: ResponseCode.ERROR_POS.value,
        ResponseCode.NETWORK_ERROR: ResponseCode.NETWORK_ERROR.value,
        ResponseCode.ERROR: ResponseCode.ERROR.value,
    }
)

Construct_StatusCode = Mapping(
    Byte,
    {
        StatusCode.Y: StatusCode.Y.value,
        StatusCode.N: StatusCode.N.value,
    }
)

Construct_AuthorizationType = Mapping(
    Byte,
    {
        AuthorizationType.PRE_AUTH: AuthorizationType.PRE_AUTH.value,
        AuthorizationType.PURCHASE: AuthorizationType.PURCHASE.value,
    }
)
