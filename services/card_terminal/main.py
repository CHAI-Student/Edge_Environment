import asyncio
import logging
import sys

from datetime import datetime

from payment import CommunicationManager


logging.basicConfig(level=logging.DEBUG)

logger = logging.getLogger(__name__)

async def run_cat_server(comm: CommunicationManager):
    try:
        server = await asyncio.start_server(comm.run, "0.0.0.0", 5000)
        print("Server running on port 5000...")
        async with server:
            await server.serve_forever()
    except Exception as e:
        print(f"Server error: {e}")

def closure_handle_api(comm: CommunicationManager):
    async def handle_api(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        pass
    return handle_api

async def run_api_server(comm: CommunicationManager):
    handle_api = closure_handle_api(comm)

    try:
        server = await asyncio.start_server(handle_api, "127.0.0.1", 30000)
        print("API Server running on port 30000...")
        async with server:
            await server.serve_forever()
    except Exception as e:
        print(f"API Server error: {e}")

async def main():
    pass

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")