import asyncio

from .data_sources import DataSourceError, DataSourceResult

class StreamQueue(asyncio.Queue):
    def __init__(self, maxsize: int = 0):
        super().__init__(maxsize=maxsize)
        self._shutdown = False

    def get_nowait(self):
        item: DataSourceResult | DataSourceError = super().get_nowait()
        if isinstance(item, DataSourceError):
            raise item.error
        return item.data, item.timestamp

    def shutdown(self):
        """Mark the queue as shutdown and clear pending items."""
        self._shutdown = True
        # Clear any remaining items in the queue
        while not self.empty():
            try:
                self.get_nowait()
            except asyncio.QueueEmpty:
                break

    def is_shutdown(self) -> bool:
        """Check if the queue has been shutdown."""
        return self._shutdown
