from construct import Byte, Bytes, Enum, Int16ub, Mapping

MessageType = Mapping(Bytes(2), {
    0: b"10", # Request
    1: b"20", # Response
})

StatusCode = Enum(Byte,
    Y = 0x59, # 'Y'
    N = 0x4E, # 'N'
)

ResponseCode = Enum(Byte,
    SUCCESS             = 0x00,
    TIMEOUT             = 0xB0,
    CANCEL              = 0xB1,
    CONDITION_FAIL      = 0xB2,
    FORMAT_ERROR        = 0xB3,
    SERVICE_UNAVAILABLE = 0xB4,
    ERROR_RF            = 0xB5,
    ERROR_VAN           = 0xB6,
    ERROR_POS           = 0xC0,
    ERROR_NETWORK       = 0xC1,
    ERROR               = 0xFF,
)

AuthorizationType = Enum(Byte,
    PRE_AUTH = 0x00,
    APPROVAL = 0x01,
)