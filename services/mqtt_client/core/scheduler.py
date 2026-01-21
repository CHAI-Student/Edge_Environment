import asyncio
from aiomqtt import Client
from typing import Callable


class Scheduler:
    def __init__(self):
        self.client = None
        self.schedules = []
        self._tasks = set()

    def register(self, /, publish_topic: str, interval: float, **kwargs):
        def decorator(func: Callable):
            async def schedule():
                assert self.client is not None
                while True:
                    await asyncio.sleep(interval)
                    result = await func()
                    if result is not None:
                        await self.client.publish(publish_topic, result, **kwargs)

            self.schedules.append(schedule)
            return func

        return decorator

    async def run(self, client: Client):
        self.client = client

        try:
            for schedule in self.schedules:
                task = asyncio.create_task(schedule())
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)
        except asyncio.CancelledError:
            asyncio.gather(*self._tasks, return_exceptions=True)
            raise

    def remaining_tasks(self):
        return len(self._tasks)
