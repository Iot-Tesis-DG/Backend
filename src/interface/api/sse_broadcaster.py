import asyncio
import json


class SSEBroadcaster:
    """Difunde eventos de lecturas térmicas a todos los clientes SSE conectados."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    async def publicar(self, evento: dict) -> None:
        mensaje = json.dumps(evento, default=str, ensure_ascii=False)
        for queue in list(self._subscribers):
            if queue.full():
                continue
            await queue.put(mensaje)
