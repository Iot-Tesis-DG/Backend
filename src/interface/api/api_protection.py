from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from src.infrastructure.config import Settings
from src.infrastructure.security.rate_limiter import SlidingWindowRateLimiter

# Los probes de disponibilidad de la plataforma no consumen cuota.
_RUTAS_EXENTAS = ("/health",)


class _CuerpoDemasiadoGrande(Exception):
    pass


class LimiteCuerpoASGI:
    """Cuenta bytes realmente recibidos, incluso con transferencias chunked.

    ``Content-Length`` solo permite rechazar antes. Este límite cubre el caso
    en que el cliente omite o miente en esa cabecera antes de que FastAPI
    deserialice el cuerpo.
    """

    def __init__(self, app, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        recibidos = 0
        respuesta_iniciada = False

        async def receive_limitado():
            nonlocal recibidos
            message = await receive()
            if message["type"] == "http.request":
                recibidos += len(message.get("body", b""))
                if recibidos > self.max_bytes:
                    raise _CuerpoDemasiadoGrande
            return message

        async def send_observado(message):
            nonlocal respuesta_iniciada
            if message["type"] == "http.response.start":
                respuesta_iniciada = True
            await send(message)

        try:
            await self.app(scope, receive_limitado, send_observado)
        except _CuerpoDemasiadoGrande:
            if not respuesta_iniciada:
                await JSONResponse(
                    status_code=413,
                    content={"detail": "Cuerpo de la solicitud demasiado grande."},
                )(scope, receive, send)


def instalar_proteccion_api(app: FastAPI, settings: Settings) -> None:
    """Controles de disponibilidad de capa aplicación (OWASP API4:2023):

    - Límite global de solicitudes por IP con ventana deslizante. A diferencia
      del limitador de login (que solo cuenta fallos), aquí cuenta toda
      solicitud: su objetivo es absorber scraping/flooding, no fuerza bruta.
    - Límite de tamaño del cuerpo: los payloads legítimos del sistema (lecturas
      IoT, formularios) son de unos pocos KB; se rechaza temprano lo demás.
    """

    app.add_middleware(LimiteCuerpoASGI, max_bytes=settings.max_body_bytes)
    limiter = SlidingWindowRateLimiter(
        max_intentos=settings.api_rate_limit_max_solicitudes,
        ventana_segundos=settings.api_rate_limit_ventana_segundos,
        max_claves=settings.security_state_max_entries,
    )
    app.state.api_rate_limiter = limiter

    @app.middleware("http")
    async def proteccion_api(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path in _RUTAS_EXENTAS:
            return await call_next(request)

        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                longitud = int(content_length)
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Content-Length inválido."},
                )
            if longitud < 0:
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Content-Length inválido."},
                )
            if longitud > settings.max_body_bytes:
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Cuerpo de la solicitud demasiado grande."},
                )

        if settings.api_rate_limit_habilitado:
            ip = request.client.host if request.client else "desconocida"
            if limiter.bloqueado(ip):
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Demasiadas solicitudes. Intenta nuevamente en unos segundos."},
                    headers={"Retry-After": str(limiter.segundos_para_reintentar(ip))},
                )
            limiter.registrar_fallo(ip)  # aquí cada solicitud cuenta para la ventana

        return await call_next(request)
