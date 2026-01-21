import asyncio
from aiomqtt import Client

from .router import Router
from .scheduler import Scheduler


class Core:
    def __init__(self):
        self.router = Router()
        self.router_task = None

        self.scheduler = Scheduler()
        self.scheduler_task = None

    async def dispatch(self, signal: str):
        if signal == "REBOOT":
            pass
        else:
            pass

    async def prepare_reboot(self):
        # Logic to prepare for reboot, such as shutting down services
        pass

    async def run(self, client: Client):
        self.router_task = asyncio.create_task(self.router.run(client))
        self.scheduler_task = asyncio.create_task(self.scheduler.run(client))

        # Wait for both tasks
        await asyncio.gather(self.router_task, self.scheduler_task)


core = Core()
