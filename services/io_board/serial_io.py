import asyncio

import construct
import serial
import serial_asyncio
from protocol import RequestProtocol, ResponseProtocol

serial_mutex = asyncio.Lock()

configuration = {
    "url": "/dev/ttyUSB0",
    "baudrate": 38400,
}


class SerialIOError(Exception):
    pass


def configure_serial(url: str, baudrate: int):
    configuration["url"] = url
    configuration["baudrate"] = baudrate


async def _fetch(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter, message: bytes
) -> bytes:
    writer.write(message)
    await writer.drain()
    response = b""
    response += await asyncio.wait_for(
        asyncio.create_task(reader.readexactly(1)), timeout=0.5
    )  # Read Start of Text
    response += await asyncio.wait_for(
        asyncio.create_task(reader.readuntil(b"\x03")), timeout=2.0
    )  # Read until Start of Text
    response += await asyncio.wait_for(
        asyncio.create_task(reader.readexactly(1)), timeout=0.5
    )  # Read ETX and LRC
    return response


async def fetch(message: bytes) -> bytes:
    async with serial_mutex:
        try:
            reader, writer = await serial_asyncio.open_serial_connection(
                url=configuration["url"],
                baudrate=configuration["baudrate"],
            )
        except serial.SerialException as e:
            raise SerialIOError(
                f"Serial IO Error: Failed to open serial port {configuration['url']}"
            ) from e
        try:
            retry = 1
            while not writer.is_closing() and retry <= 3:
                try:
                    response = await _fetch(reader, writer, message)
                    return response
                except (asyncio.IncompleteReadError, asyncio.TimeoutError) as e:
                    print(f"Serial IO Warning: Retry {retry} fetching data")
                    if retry >= 3:
                        raise SerialIOError(
                            "Serial IO Error: Failed to fetch data"
                        ) from e
                retry += 1
                await asyncio.sleep(0.1)
        finally:
            writer.close()
            await writer.wait_closed()
    raise SerialIOError("Serial IO Error: Failed to fetch data")


async def _io_board_send_command(command: str, subcommand: str, data: dict):
    try:
        req_message = RequestProtocol.build(
            dict(COMMAND=command, SUBCOMMAND=subcommand, DATA=data)
        )
    except construct.ConstructError as e:
        raise SerialIOError("Serial IO Error: Failed to build IO Board request") from e
    resp_message = await fetch(req_message)
    try:
        resp = ResponseProtocol.parse(resp_message)
    except construct.ConstructError as e:
        raise SerialIOError("Serial IO Error: Failed to parse IO Board response") from e
    return resp


async def io_board_init():
    resp = await _io_board_send_command("MC", "PD", {})


async def io_board_set_door(state: str):
    resp = await _io_board_send_command("MC", "DC", dict(DOOR=state))
    return resp.DATA.DOOR


async def io_board_calibrate():
    resp = await _io_board_send_command("MC", "LZ", {})


async def io_board_set_manufacturing_number(manufacturing_number: str):
    resp = await _io_board_send_command(
        "MC", "WP", dict(PRODUCT_ID=manufacturing_number)
    )
    return resp.DATA.PRODUCT_ID


async def io_board_clear_errors():
    resp = await _io_board_send_command("MC", "EZ", {})


async def io_board_reboot():
    resp = await _io_board_send_command("MC", "RT", {})


async def io_board_get_product_info():
    resp = await _io_board_send_command("RQ", "MI", {})
    return dict(
        product_id=resp.DATA.PRODUCT_ID,
        sw_version=resp.DATA.SW_VERSION,
    )


async def io_board_get_loadcells():
    resp = await _io_board_send_command("RQ", "IW", {})
    return list(resp.DATA.LOADCELLS)


async def io_board_get_status():
    resp = await _io_board_send_command("RQ", "ID", {})
    return dict(
        door=resp.DATA.DOOR,
        deadbolt=resp.DATA.DEADBOLT,
    )


async def io_board_get_errors():
    resp = await _io_board_send_command("RQ", "ER", {})
    return list(resp.DATA.ERRORS)
