from functools import reduce

from construct import (
    Adapter,
    Byte,
    Bytes,
    Checksum,
    Const,
    Int16ub,
    PaddedString,
    Rebuild,
    Struct,
)

from .const import MessageType

class BCD(Adapter):
    def _encode(self, obj, context, path):
        encoded, digit_pos = 0, 0
        while obj > 0:
            digit = obj % 10
            encoded |= digit << (digit_pos * 4)
            obj //= 10
            digit_pos += 1
        return encoded

    def _decode(self, obj, context, path):
        decoded, multiplier = 0, 1
        while obj > 0:
            digit = obj & 0x0F
            decoded += digit * multiplier
            obj >>= 4
            multiplier *= 10
        return decoded


def seek_and_read(stream, offset, length):
    org_pos = stream.tell()
    stream.seek(offset)
    data = stream.read(length)
    stream.seek(org_pos)
    return data

Length = BCD(Int16ub)

Protocol = Struct(
    Const(b"\x02"),
    "length" / Rebuild(Length, lambda ctx: len(ctx.payload) + 9),
    "service_code" / PaddedString(2, "ascii"),
    "message_type" / MessageType,
    "payload" / Bytes(lambda ctx: ctx.length - 9),
    Const(b"\x03"),
    Checksum(
        Byte,
        lambda data: reduce(lambda x, y: x ^ y, data),
        lambda ctx: seek_and_read(ctx._io, 1, ctx.length - 2),
    ),
)

