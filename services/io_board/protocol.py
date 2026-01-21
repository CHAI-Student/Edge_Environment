from functools import reduce

from construct import (
    Array,
    Byte,
    Checksum,
    Const,
    Enum,
    PaddedString,
    Pass,
    Struct,
    Switch,
    Tell,
)


def seek_and_read(stream, offset, length):
    org_pos = stream.tell()
    stream.seek(offset)
    data = stream.read(length)
    stream.seek(org_pos)
    return data


RequestProtocol = Struct(
    Const(b"\x02"),  # Start of Text
    "COMMAND" / PaddedString(2, "ascii"),  # Command Code
    "SUBCOMMAND" / PaddedString(2, "ascii"),  # Subcommand Code
    "DATA"
    / Switch(
        lambda ctx: ctx.COMMAND + ctx.SUBCOMMAND,
        {
            "MCPD": Pass,
            "MCDC": Struct(
                "DOOR" / Enum(Byte, OPEN=ord("O"), CLOSE=ord("C")),
            ),
            "MCLZ": Pass,
            "MCWP": Struct(
                "PRODUCT_ID" / PaddedString(11, "ascii"),
            ),
            "MCEZ": Pass,
            "MCRT": Pass,
            "RQMI": Pass,
            "RQIW": Pass,
            "RQID": Pass,
            "RQER": Pass,
        },
    ),
    Const(b"\x03"),  # End of Text
    "_length" / Tell,
    Checksum(
        Byte,
        lambda data: reduce(lambda x, y: x ^ y, data),
        lambda ctx: seek_and_read(ctx._io, 1, ctx._length - 1),
    ),
)

ResponseProtocol = Struct(
    Const(b"\x02"),  # Start of Text
    "COMMAND" / PaddedString(2, "ascii"),  # Command Code
    "SUBCOMMAND" / PaddedString(2, "ascii"),  # Subcommand Code
    "DATA"
    / Switch(
        lambda this: this.COMMAND + this.SUBCOMMAND,
        {
            "MCPD": Pass,
            "MCDC": Struct(
                "DOOR" / Enum(Byte, OPEN=ord("O"), CLOSE=ord("C")),
            ),
            "MCLZ": Pass,
            "MCWP": Struct(
                "PRODUCT_ID" / PaddedString(11, "ascii"),
            ),
            "MCEZ": Pass,
            "MCRT": Pass,
            "RQMI": Struct(
                "PRODUCT_ID" / PaddedString(11, "ascii"),
                "SW_VERSION" / PaddedString(2, "ascii"),
            ),
            "RQIW": Struct(
                "LOADCELLS" / Array(10, PaddedString(6, "ascii")),
            ),
            "RQID": Struct(
                "DOOR" / PaddedString(6, "ascii"),
                "DEADBOLT" / PaddedString(6, "ascii"),
            ),
            "RQER": Struct(
                "ERRORS" / Array(4, PaddedString(4, "ascii")),
            ),
        },
    ),
    Const(b"\x03"),  # End of Text
    "_length" / Tell,
    Checksum(
        Byte,
        lambda data: reduce(lambda x, y: x ^ y, data),
        lambda ctx: seek_and_read(ctx._io, 1, ctx._length - 1),
    ),
)
