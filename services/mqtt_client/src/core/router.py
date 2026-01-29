import asyncio
from aiomqtt import Client
from typing import Callable

from config import settings


class Router:
    def __init__(self):
        self.client: Client | None = None
        self.subscribes = []
        self.handlers = {}
        self._tasks = set()

    def _resolve_topic(self, topic: str) -> str:
        """Replace placeholders in topic with actual values from settings.

        Matches Node.js pattern: chai/device/${deviceIdx}/...
        """
        return topic.format(
            DEVICE_ID=settings.device_idx,
            DIVISION_ID=settings.division_idx,
        )

    def register(
        self, /, subscribe_topic: str, publish_topic: str | None = None, qos: int = 1, **kwargs
    ):
        """Register a handler for MQTT topic.

        Args:
            subscribe_topic: Topic to subscribe (supports {DEVICE_ID} placeholder)
            publish_topic: Topic to publish response (supports {DEVICE_ID} placeholder)
            qos: QoS level (default: 1 to match Node.js for commands)
        """
        # Resolve placeholders at registration time
        resolved_sub = self._resolve_topic(subscribe_topic)
        resolved_pub = self._resolve_topic(publish_topic) if publish_topic else None

        def decorator(func: Callable):
            async def subscribe():
                assert self.client is not None
                await self.client.subscribe(resolved_sub, qos=qos, **kwargs)

            self.subscribes.append(subscribe)

            async def handler(*args, **inner_kwargs):
                assert self.client is not None
                result = await func(*args, **inner_kwargs)
                if resolved_pub and result is not None:
                    await self.client.publish(resolved_pub, result, qos=qos, **kwargs)
                return result

            self.handlers[resolved_sub] = handler
            return func

        return decorator

    async def run(self, client: Client):
        self.client = client

        for subscribe in self.subscribes:
            await subscribe()

        async for message in self.client.messages:
            # Convert Topic object to string for handler lookup
            topic_str = str(message.topic)
            if handler := self.handlers.get(topic_str):
                task = asyncio.create_task(handler(message.payload))
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)

    def remaining_tasks(self):
        return len(self._tasks)
