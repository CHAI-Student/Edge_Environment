import asyncio
from aiomqtt import Client
from typing import Callable


class Router:
    def __init__(self):
        self.client: Client | None = None
        self.subscribes = []
        self.handlers = {}
        self._tasks = set()

    def register(
        self, /, subscribe_topic: str, publish_topic: str | None = None, **kwargs
    ):
        def decorator(func: Callable):
            async def subscribe():
                assert self.client is not None
                await self.client.subscribe(subscribe_topic, **kwargs)

            self.subscribes.append(subscribe)

            async def handler(*args, **inner_kwargs):
                assert self.client is not None
                result = await func(*args, **inner_kwargs)
                if publish_topic and result is not None:
                    await self.client.publish(publish_topic, result, **kwargs)
                return result

            self.handlers[subscribe_topic] = handler
            return func

        return decorator

    async def run(self, client: Client):
        self.client = client

        for subscribe in self.subscribes:
            await subscribe()

        async for message in self.client.messages:
            if handler := self.handlers.get(message.topic):
                task = asyncio.create_task(handler(message.payload))
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)

    def remaining_tasks(self):
        return len(self._tasks)
