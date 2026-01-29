import logging
from functools import reduce

from construct import (
    Adapter,
    Byte,
    Bytes,
    Checksum,
    Const,
    PaddedString,
    Rebuild,
    Struct,
)

from .const import ETX, STX, Construct_MessageType

logger = logging.getLogger(__name__)


class BCD(Adapter):
    def _encode(self, obj, context, path):
        size = self._sizeof(context, path)
        encoded = bytearray(size)
        for i in range(size - 1, -1, -1):
            obj, remainder = divmod(obj, 100)
            encoded[i] = (remainder // 10 << 4) + (remainder % 10)
        return bytes(encoded)

    def _decode(self, obj, context, path):
        decoded = 0
        for i in range(self._sizeof(context, path)):
            octet = obj[i]
            decoded *= 100
            decoded += (octet >> 4) * 10 + (octet & 0x0F)
        return decoded


def seek_and_read(stream, offset, length):
    org_pos = stream.tell()
    stream.seek(offset)
    data = stream.read(length)
    stream.seek(org_pos)
    return data


Length = BCD(Byte[2])

Protocol = Struct(
    Const(STX),
    "length" / Rebuild(Length, lambda ctx: len(ctx.payload) + 9),
    "service_code" / PaddedString(2, "ascii"),
    "message_type" / Construct_MessageType,
    "payload" / Bytes(lambda ctx: ctx.length - 9),
    Const(ETX),
    Checksum(
        Byte,
        lambda data: reduce(lambda x, y: x ^ y, data),
        lambda ctx: seek_and_read(ctx._io, 1, ctx.length - 2),
    ),
)
