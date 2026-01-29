from construct import (
    Const,
    GreedyBytes,
    GreedyString,
    NullTerminated,
    PaddedString,
    Select,
    Struct,
)

from .const import (
    FS,
    RS,
    Construct_AuthorizationType,
    Construct_ResponseCode,
    Construct_StatusCode,
)

ErrorPayload = Struct(
    "status" / Const(b"N"),
    Const(FS),
    "response_code" / Construct_ResponseCode,
    Const(RS),
    "message" / NullTerminated(GreedyString("euc-kr"), term=FS),
    # Const(FS),
)

CardInfo = Struct(
    "serial_number" / NullTerminated(GreedyString("ascii"), term=RS),
    # Const(RS),
    "acquirer_id" / NullTerminated(GreedyString("ascii"), term=RS),
    # Const(RS),
    "acquirer_name" / NullTerminated(GreedyString("euc-kr"), term=RS),
    # Const(RS),
    "issuer_id" / NullTerminated(GreedyString("ascii"), term=RS),
    # Const(RS),
    "issuer_name" / NullTerminated(GreedyString("euc-kr"), term=RS),
    # Const(RS),
    "merchant_id" / GreedyString("ascii"),
)

AgeCheckRequest = Struct(
    Const(FS),
)
AgeCheckResponse = Struct(
    Const(FS),
    "qr_data" / NullTerminated(GreedyBytes, term=FS),
    # Const(FS),
    "message" / NullTerminated(GreedyString("euc-kr"), term=FS),
    # Const(FS),
)

TransactionTokenInitilizeRequest = Struct(
    Const(FS),
)
TransactionTokenInitilizeResponse = Struct(
    Const(FS),
    "message" / NullTerminated(GreedyString("euc-kr"), term=FS),
    # Const(FS),
)

TransactionTokenGenerateRequest = Struct(
    "message" / NullTerminated(GreedyString("euc-kr"), term=FS),
    # Const(FS),
)
TransactionTokenGenerateResponse = Struct(
    "status" / Construct_StatusCode,
    Const(FS),
    "vankey_hash" / NullTerminated(GreedyString("ascii"), term=FS),
    # Const(FS),
    "card_info" / NullTerminated(Select(CardInfo, GreedyString("ascii")), term=FS),
    # Const(FS),
    "response_code" / Construct_ResponseCode,
    Const(RS),
    "message" / NullTerminated(GreedyString("euc-kr"), term=FS),
    # Const(FS),
)

TransactionTokenApproveRequest = Struct(
    "amount" / NullTerminated(GreedyString("ascii"), term=FS),
    # Const(FS),
    "vankey_hash" / NullTerminated(GreedyString("ascii"), term=FS),
    # Const(FS),
    "message" / NullTerminated(GreedyString("euc-kr"), term=FS),
    # Const(FS),
)
TransactionTokenApproveResponse = Struct(
    "status" / Construct_StatusCode,
    Const(FS),
    "authorization_number" / NullTerminated(GreedyString("ascii"), term=FS),
    # Const(FS),
    "card_info" / NullTerminated(Select(CardInfo, GreedyString("ascii")), term=FS),
    # Const(FS),
    "vankey" / NullTerminated(GreedyString("ascii"), term=FS),
    # Const(FS),
    "response_code" / Construct_ResponseCode,
    Const(RS),
    "message" / NullTerminated(GreedyString("euc-kr"), term=FS),
    # Const(FS),
)

TransactionTokenCancelRequest = Struct(
    "amount" / NullTerminated(GreedyString("ascii"), term=FS),
    # Const(FS),
    "original_authorization_number" / PaddedString(8, "ascii"),
    Const(FS),
    "original_authorization_date" / PaddedString(6, "ascii"),
    Const(FS),
    "vankey_hash" / PaddedString(24, "ascii"),
    Const(FS),
)
TransactionTokenCancelResponse = Struct(
    "status" / Construct_StatusCode,
    Const(FS),
    "card_info" / NullTerminated(Select(CardInfo, GreedyString("ascii")), term=FS),
    # Const(FS),
    "vankey" / NullTerminated(GreedyString("ascii"), term=FS),
    # Const(FS),
    "response_code" / Construct_ResponseCode,
    Const(RS),
    "message" / NullTerminated(GreedyString("euc-kr"), term=FS),
    # Const(FS),
)

TransactionRFIDInitilizeRequest = Struct(
    "data" / PaddedString(10, "ascii"),
    Const(FS),
)

TransactionSPayInitilizeRequest = Struct(
    Const(FS),
)
TransactionSPayInitilizeResponse = Struct(
    Const(FS),
    "message" / NullTerminated(GreedyString("euc-kr"), term=FS),
    # Const(FS),
)

TransactionSPayApproveRequest = Struct(
    "amount" / NullTerminated(GreedyString("ascii"), term=FS),
    # Const(FS),
    "authorization_type" / Construct_AuthorizationType,
    Const(FS),
    "message" / NullTerminated(GreedyString("euc-kr"), term=FS),
    # Const(FS),
)
TransactionSPayApproveResponse = Struct(
    "status" / Construct_StatusCode,
    Const(FS),
    "authorization_number" / NullTerminated(GreedyString("ascii"), term=FS),
    # Const(FS),
    "vankey" / NullTerminated(GreedyString("ascii"), term=FS),
    # Const(FS),
    "card_info" / NullTerminated(Select(CardInfo, GreedyString("ascii")), term=FS),
    # Const(FS),
    "response_code" / Construct_ResponseCode,
    Const(RS),
    "message" / NullTerminated(GreedyString("euc-kr"), term=FS),
    # Const(FS),
)

TransactionSPayCancelRequest = Struct(
    "amount" / NullTerminated(GreedyString("ascii"), term=FS),
    # Const(FS),
    "original_authorization_number" / PaddedString(8, "ascii"),
    Const(FS),
    "original_authorization_date" / PaddedString(6, "ascii"),
    Const(FS),
    "vankey" / PaddedString(16, "ascii"),
    Const(FS),
)
TransactionSPayCancelResponse = Struct(
    "status" / Construct_StatusCode,
    Const(FS),
    "card_info" / NullTerminated(Select(CardInfo, GreedyString("ascii")), term=FS),
    # Const(FS),
    "vankey" / NullTerminated(GreedyString("ascii"), term=FS),
    # Const(FS),
    "response_code" / Construct_ResponseCode,
    Const(RS),
    "message" / NullTerminated(GreedyString("euc-kr"), term=FS),
    # Const(FS),
)

DeviceCheckRequest = Struct(
    "message" / NullTerminated(GreedyString("euc-kr"), term=FS),
    # Const(FS),
)
DeviceCheckResponse = Struct(
    "response_code" / Construct_ResponseCode,
    Const(FS),
)
