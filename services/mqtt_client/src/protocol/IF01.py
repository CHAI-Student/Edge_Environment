import asyncio

from aiomqtt.types import PayloadType
from pydantic_core import ValidationError

from core import core
from config import settings
from util import VerificationError

from .protocol import *


IF_ID = "IF_01"
IF_SYSID = "45BDA-12A3DASD-1231-1E12-3123D3DAZ23"
IF_HOST = "CRKPNTCHAI"
IF_DATE = "20240503152229"

HEADER = {
    "IF_ID": IF_ID,
    "IF_SYSID": IF_SYSID,
    "IF_HOST": IF_HOST,
    "IF_DATE": IF_DATE,
}

# 전역 상태 보호를 위한 Lock
__reboot_lock = asyncio.Lock()
__is_rebooting = False


@core.router.register(
    subscribe_topic="chai/device/{DEVICE_ID}/req/reboot",
    publish_topic="chai/device/{DEVICE_ID}/ack/reboot",
)
async def reboot_handler(payload: PayloadType):
    global __is_rebooting

    if not isinstance(payload, (str, bytes, bytearray)):
        return None

    try:
        req_message = ReqMessage.model_validate_json(payload)
    except ValidationError as e:
        return None

    if (
        req_message.DATA.division_idx != settings.division_idx
        or req_message.DATA.device_idx != settings.device_idx
    ):
        return None

    # Lock을 사용하여 동시 접근 방지
    async with __reboot_lock:
        if __is_rebooting:
            return AckMessage.model_validate(
                {
                    "HEADER": HEADER,
                    "DATA": {
                        "division_idx": settings.division_idx,
                        "device_idx": settings.device_idx,
                        "result_cd": "F",
                        "result_msg": "reboot fail: another reboot in progress",
                    },
                }
            ).model_dump_json()

        try:
            await ensure_conditions_for_reboot()
        except VerificationError as e:
            return AckMessage.model_validate(
                {
                    "HEADER": HEADER,
                    "DATA": {
                        "division_idx": settings.division_idx,
                        "device_idx": settings.device_idx,
                        "result_cd": "F",
                        "result_msg": f"reboot fail: {str(e)}",
                    },
                }
            ).model_dump_json()

        # Reboot 상태 설정
        __is_rebooting = True

    # Lock 해제 후 실제 reboot 수행
    try:
        await core.dispatch("REBOOT")
    finally:
        async with __reboot_lock:
            __is_rebooting = False

    return AckMessage.model_validate(
        {
            "HEADER": HEADER,
            "DATA": {
                "division_idx": settings.division_idx,
                "device_idx": settings.device_idx,
                "result_cd": "S",
                "result_msg": "reboot success",
            },
        }
    ).model_dump_json()


async def ensure_card_terminal_idle():
    # check payment terminal status
    pass


async def ensure_transaction_durable():
    # ensure all transactions are durable (acked from server)
    pass


async def ensure_deadbolt_closed():
    # check deadbolt status
    pass


async def ensure_conditions_for_reboot():
    results = await asyncio.gather(
        ensure_card_terminal_idle(),
        ensure_transaction_durable(),
        ensure_deadbolt_closed(),
        return_exceptions=True,
    )

    if any(isinstance(r, Exception) for r in results):
        errors = [str(r) for r in results if isinstance(r, Exception)]
        raise VerificationError("; ".join(errors))
