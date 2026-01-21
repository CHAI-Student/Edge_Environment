from construct import (
    Bytes,
    Const,
    Default,
    GreedyBytes,
    GreedyString,
    If,
    NullTerminated,
    Optional,
    PaddedString,
    Struct,
)

from .const import ResponseCode, AuthorizationType, StatusCode

Notification = Struct(
    "response_code" / ResponseCode,
    Const(b"\x1e"),
    "message" / GreedyString("euc-kr"),
)

Error = Struct(
    "status" / Const(b"N"),
    Const(b"\x1c"),
    "notification" / NullTerminated(Notification, term=b"\x1c"),
    # Const(b"\x1c"),
)

CardInfo = Struct(
    "serial_number" / NullTerminated(GreedyString("ascii"), term=b"\x1e"),
    # Const(b"\x1e"),
    "acquirer_id" / PaddedString(3, "ascii"),
    Const(b"\x1e"),
    "acquirer_name" / NullTerminated(GreedyString("euc-kr"), term=b"\x1e"),
    # Const(b"\x1e"),
    "issuer_id" / PaddedString(3, "ascii"),
    Const(b"\x1e"),
    "issuer_name" / NullTerminated(GreedyString("euc-kr"), term=b"\x1e"),
    # Const(b"\x1e"),
    "merchant_id" / GreedyString("ascii"),
)

PayloadStructures = {}

PayloadStructures["AC"] = AgeCheck = [
    Struct(
        Const(b"\x1c"),
    ),
    Struct(
        Const(b"\x1c"),
        "qr_data" / NullTerminated(GreedyBytes, term=b"\x1c"),
        # Const(b"\x1c"),
        "notification" / NullTerminated(Notification, term=b"\x1c"),
        # Const(b"\x1c"),
    ),
]

PayloadStructures["PP"] = [
    Struct(
        Const(b"\x1c"),
    ),
    Struct(
        Const(b"\x1c"),
        "message" / NullTerminated(GreedyString("euc-kr"), term=b"\x1c"),
        # Const(b"\x1c"),
    ),
]

PayloadStructures["PS"] = PaymentTokenStart = [
    Struct(
        Const(b"\x1c"),
    ),
    Struct(
        Const(b"\x1c"),
        "message" / NullTerminated(GreedyString("euc-kr"), term=b"\x1c"),
        # Const(b"\x1c"),
    ),
]

PayloadStructures["TQ"] = PaymentTokenCreate = [
    Struct(
        "message" / NullTerminated(Default(GreedyString("euc-kr"), ""), term=b"\x1c"),
        # Const(b"\x1c"),
    ),
    Struct(
        "status" / StatusCode,
        Const(b"\x1c"),
        "vankey_hash" / If(lambda ctx: ctx.status == "Y", Bytes(24)),
        Const(b"\x1c"),
        "card_info" / NullTerminated(If(lambda ctx: ctx.status == "Y", CardInfo), term=b"\x1c"),
        # Const(b"\x1c"),
        "notification" / NullTerminated(Notification, term=b"\x1c"),
        # Const(b"\x1c"),
    ),
]

PayloadStructures["D8"] = PaymentTokenApprove = [
    Struct(
        "amount" / NullTerminated(GreedyString("ascii"), term=b"\x1c"),
        # Const(b"\x1c"),
        "vankey_hash" / Optional(Bytes(24)),
        Const(b"\x1c"),
    ),
    Struct(
        "status" / StatusCode,
        Const(b"\x1c"),
        "authorization_number" / If(lambda ctx: ctx.status == "Y", Bytes(8)),
        Const(b"\x1c"),
        "card_info" / NullTerminated(If(lambda ctx: ctx.status == "Y", CardInfo), term=b"\x1c"),
        # Const(b"\x1c"),
        "vankey" / Optional(Bytes(16)),
        Const(b"\x1c"),
        "notification" / NullTerminated(Notification, term=b"\x1c"),
        # Const(b"\x1c"),
    ),
]

PayloadStructures["D9"] = PaymentTokenCancel = [
    Struct(
        "amount" / NullTerminated(GreedyString("ascii"), term=b"\x1c"),
        # Const(b"\x1c"),
        "original_authorization_number" / Bytes(8),
        Const(b"\x1c"),
        "original_authorization_date" / PaddedString(6, "ascii"),
        Const(b"\x1c"),
        "vankey_hash" / Optional(Bytes(24)),
        Const(b"\x1c"),
    ),
    Struct(
        "status" / StatusCode,
        Const(b"\x1c"),
        "card_info" / NullTerminated(If(lambda ctx: ctx.status == "Y", CardInfo), term=b"\x1c"),
        # Const(b"\x1c"),
        "vankey" / If(lambda ctx: ctx.status == "Y", Bytes(16)),
        Const(b"\x1c"),
        "notification" / NullTerminated(Notification, term=b"\x1c"),
        # Const(b"\x1c"),
    ),
]

PayloadStructures["PA"] = PaymentSamsungStart = [
    Struct(
        Const(b"\x1c"),
    ),
    Struct(
        Const(b"\x1c"),
        "message" / NullTerminated(GreedyString("euc-kr"), term=b"\x1c"),
        # Const(b"\x1c"),
    ),
]

PayloadStructures["D1"] = PaymentSamsungApprove = [
    Struct(
        "amount" / NullTerminated(GreedyString("ascii"), term=b"\x1c"),
        # Const(b"\x1c"),
        "authorization_type" / AuthorizationType,
        Const(b"\x1c"),
        "message" / NullTerminated(GreedyString("euc-kr"), term=b"\x1c"),
        # Const(b"\x1c"),
    ),
    Struct(
        "status" / StatusCode,
        Const(b"\x1c"),
        "authorization_number" / Optional(Bytes(8)),
        Const(b"\x1c"),
        "vankey" / Optional(Bytes(16)),
        Const(b"\x1c"),
        "card_info" / NullTerminated(Optional(CardInfo), term=b"\x1c"),
        # Const(b"\x1c"),
        "notification" / NullTerminated(Notification, term=b"\x1c"),
        # Const(b"\x1c"),
    ),
]

PayloadStructures["D7"] = PaymentSamsungCancel = [
    Struct(
        "amount" / NullTerminated(GreedyString("ascii"), term=b"\x1c"),
        # Const(b"\x1c"),
        "original_authorization_number" / Bytes(8),
        Const(b"\x1c"),
        "original_authorization_date" / PaddedString(6, "ascii"),
        Const(b"\x1c"),
        "vankey" / Optional(Bytes(16)),
        Const(b"\x1c"),
    ),
    Struct(
        "status" / StatusCode,
        Const(b"\x1c"),
        "card_info" / NullTerminated(Optional(CardInfo), term=b"\x1c"),
        # Const(b"\x1c"),
        "vankey" / Optional(Bytes(16)),
        Const(b"\x1c"),
        "notification" / NullTerminated(Notification, term=b"\x1c"),
        # Const(b"\x1c"),
    ),
]

PayloadStructures["PC"] = DeviceCheck = [
    Struct(
        "message" / NullTerminated(GreedyString("euc-kr"), term=b"\x1c"),
        # Const(b"\x1c"),
    ),
    Struct(
        "response_code" / ResponseCode,
        Const(b"\x1c"),
    ),
]

ErrorPayload = Error
