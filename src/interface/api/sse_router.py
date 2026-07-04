import asyncio
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/sse", tags=["sse"])


async def _event_stream(request: Request) -> AsyncGenerator[str, None]:
    broadcaster = request.app.state.sse_broadcaster
    queue = broadcaster.subscribe()
    try:
        while True:
            if await request.is_disconnected():
                break
            try:
                mensaje = await asyncio.wait_for(queue.get(), timeout=15.0)
                yield f"data: {mensaje}\n\n"
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"
    finally:
        broadcaster.unsubscribe(queue)


@router.get("/lecturas")
async def stream_lecturas(request: Request) -> StreamingResponse:
    """RF-11: el dashboard consume actualizaciones en tiempo real vía SSE."""
    return StreamingResponse(_event_stream(request), media_type="text/event-stream")
