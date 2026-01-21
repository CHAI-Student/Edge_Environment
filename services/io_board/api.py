import json
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from serial_io import *
from uvicorn.config import Config
from uvicorn.server import Server

app = FastAPI()


@app.exception_handler(SerialIOError)
async def ioboard_exception_handler(request, exc: SerialIOError):
    return JSONResponse(
        status_code=500,
        content={"msg": str(exc)},
    )

@app.post("/init")
async def handle_init():
    await io_board_init()


class Deadbolt(BaseModel):
    state: Literal["OPEN", "CLOSE"]
@app.post("/deadbolt")
async def handle_deadbolt(deadbolt: Deadbolt) -> Deadbolt:
    await io_board_set_door(deadbolt.state)
    status = await io_board_get_status()
    print(status)
    if status["deadbolt"] == "OPENED":
        return Deadbolt(state="OPEN")
    else:
        return Deadbolt(state="CLOSE")


@app.post("/calibrate")
async def handle_calibrate():
    await io_board_calibrate()


class ManufacturingNumber(BaseModel):
    manufacturing_number: str = Field(..., min_length=11, max_length=11)
@app.post("/manufacturing_number")
async def handle_manufacturing_number(
    manufacturing_number: ManufacturingNumber,
) -> ManufacturingNumber:
    manufacturing_number_str = manufacturing_number.manufacturing_number
    result = await io_board_set_manufacturing_number(manufacturing_number_str)
    return ManufacturingNumber(manufacturing_number=result)


@app.delete("/errors")
async def handle_clear_errors():
    await io_board_clear_errors()


@app.post("/reboot")
async def handle_reboot():
    await io_board_reboot()


class ProductInfo(BaseModel):
    product_id: str
    sw_version: str
@app.get("/product_info")
async def handle_product_info() -> ProductInfo:
    info = await io_board_get_product_info()
    return ProductInfo(
        product_id=info["product_id"],
        sw_version=info["sw_version"],
    )


class LoadCells(BaseModel):
    loadcells: list[str]
@app.get("/loadcells")
async def handle_loadcells() -> LoadCells:
    loadcells = await io_board_get_loadcells()
    return LoadCells(loadcells=loadcells)


class Status(BaseModel):
    door: str
    deadbolt: str
@app.get("/status")
async def handle_status() -> Status:
    status = await io_board_get_status()
    return Status(
        door=status["door"],
        deadbolt=status["deadbolt"],
    )


class Error(BaseModel):
    code: str
@app.get("/errors")
async def handle_errors() -> list[Error]:
    errors = await io_board_get_errors()
    return [Error(code=err) for err in errors]


@app.get("/stream/loadcells")
async def handle_stream_loadcells() -> StreamingResponse:
    # use exponential smoothing to reduce noise
    async def event_generator():
        while True:
            try:
                loadcells = await io_board_get_loadcells()
                data = json.dumps({"loadcells": loadcells})
                yield f"event: update\ndata: {data}\n\n"
            except SerialIOError as e:
                data = json.dumps({"msg": str(e)})
                yield f"event: error\ndata: {data}\n\n"
            await asyncio.sleep(0.5)
    return StreamingResponse(event_generator(), media_type="text/event-stream")


async def serve_api(host, port, log_level="info"):
    config = Config(app=app, host=host, port=port, log_level=log_level)
    server = Server(config=config)
    server.force_exit = True
    await server.serve()
