import asyncio
from collections.abc import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from src.domain.exceptions import CredencialesInvalidasError
from src.interface.api.deps import JWTHandlerDep

router = APIRouter(prefix="/api/sse", tags=["sse"])


async def _event_stream(request: Request) -> AsyncGenerator[str, None]:
    broadcaster = request.app.state.sse_broadcaster
    queue = broadcaster.subscribe()
    try:
        # Chunk inicial: fuerza el envío de headers a través de proxies y
        # dispara el evento `open` del EventSource del navegador.
        yield ": connected\n\n"
        while True:
            if await request.is_disconnected():
                break
            try:
                mensaje = await asyncio.wait_for(queue.get(), timeout=15.0)
                yield f"{mensaje}\n\n"
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"
    finally:
        broadcaster.unsubscribe(queue)


@router.get("/lecturas")
async def stream_lecturas(
    request: Request, ticket: str, jwt_handler: JWTHandlerDep
) -> StreamingResponse:
    """RF-11: el dashboard consume actualizaciones en tiempo real vía SSE.

    Requiere un ticket efímero emitido en POST /api/auth/sse-ticket porque
    EventSource no puede enviar el header Authorization. El ticket es de UN
    SOLO USO: viaja como query param (puede quedar en logs de proxies), así
    que reutilizarlo se rechaza aunque no haya expirado.
    """
    try:
        datos_ticket = jwt_handler.validar_ticket_sse(ticket)
    except CredencialesInvalidasError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc

    if not request.app.state.sse_ticket_store.consumir(
        datos_ticket.jti, datos_ticket.exp.timestamp()
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Ticket SSE ya utilizado"
        )
    return StreamingResponse(_event_stream(request), media_type="text/event-stream")
