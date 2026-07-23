import asyncio
from datetime import datetime, timezone
from uuid import UUID

from src.domain.entities.registro_trazabilidad import RegistroTrazabilidad
from src.domain.repositories.i_trazabilidad_repository import ITrazabilidadRepository
from src.domain.value_objects.hash_encadenado import HashEncadenado, timestamp_canonico

# Estrategia de cadena: GLOBAL (una única cadena para todo el sistema, no
# separada por dispositivo ni por farmacia). Decisión de diseño explícita,
# coherente con el alcance de la tesis (un solo escenario de validación).
#
# Concurrencia: leer el último hash e insertar el siguiente eslabón es una
# sección crítica de lectura-luego-escritura. Sin serializarla, dos escrituras
# casi simultáneas pueden leer el mismo previous_hash y bifurcar la cadena
# (hallazgo B-01 de la auditoría). Este backend es de un solo proceso por
# diseño (mismo supuesto ya documentado en JtiStore y SlidingWindowRateLimiter),
# así que un candado a nivel de proceso serializa correctamente todas las
# escrituras de la cadena sin depender del dialecto de base de datos (Postgres
# o SQLite en pruebas). En un despliegue multi-worker real, este candado NO
# basta (cada worker tiene su propio proceso) y debe reforzarse con un bloqueo
# a nivel de base de datos (p. ej. pg_advisory_xact_lock, ver
# infrastructure/database/repositories/trazabilidad_repository.py) —
# limitación conocida y documentada, igual que las demás estructuras en
# memoria de este prototipo.
class _CandadoDeProceso:
    """asyncio.Lock que se rebina automáticamente si cambia el event loop en
    ejecución. Un asyncio.Lock ordinario creado a nivel de módulo queda atado
    al primer loop que lo usa; en un proceso de producción real solo existe un
    loop durante toda la vida del proceso, así que esto nunca ocurre. Pero en
    la suite de pruebas, pytest-asyncio crea un loop nuevo por test, y un lock
    puramente módulo-global fallaría con 'bound to a different event loop' al
    segundo test que lo usara. Este wrapper lo hace seguro en ambos casos."""

    def __init__(self) -> None:
        self._lock: asyncio.Lock | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def _lock_actual(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        if self._lock is None or self._loop is not loop:
            self._lock = asyncio.Lock()
            self._loop = loop
        return self._lock

    async def __aenter__(self) -> None:
        await self._lock_actual().acquire()

    async def __aexit__(self, *_exc_info: object) -> None:
        self._lock_actual().release()


_CANDADO_CADENA = _CandadoDeProceso()


class RegistrarHashEncadenadoUseCase:
    """Genera un nuevo eslabón de la cadena SHA-256 para cualquier evento auditable
    (RF-14: lectura, alerta, acción correctiva, reporte, auditoría, conectividad).

    La lectura del último hash y la inserción del nuevo registro se ejecutan
    dentro de una sección crítica serializada (_CANDADO_CADENA) para impedir
    que dos eventos concurrentes bifurquen la cadena (ver comentario del módulo).
    """

    def __init__(self, trazabilidad_repository: ITrazabilidadRepository) -> None:
        self._trazabilidad_repository = trazabilidad_repository

    async def execute(
        self,
        tipo_evento: str,
        payload: dict,
        device_id: str | None = None,
        usuario_id: UUID | None = None,
        timestamp: datetime | None = None,
        previous_hash_forzado: str | None = None,
    ) -> RegistroTrazabilidad:
        """previous_hash_forzado (HU-47): permite anclar un evento de emergencia
        al último bloque ÍNTEGRO conocido en vez de al último hash almacenado
        (que puede ya ser descendiente de un registro corrupto)."""
        timestamp = timestamp or datetime.now(tz=timezone.utc)

        async def registrar() -> RegistroTrazabilidad:
            previous_hash = previous_hash_forzado or await self._trazabilidad_repository.obtener_ultimo_hash()
            hash_encadenado = HashEncadenado.encadenar(
                previous_hash, timestamp_canonico(timestamp), payload
            )
            registro = RegistroTrazabilidad(
                tipo_evento=tipo_evento,
                payload=payload,
                timestamp=timestamp,
                hash_encadenado=hash_encadenado,
                device_id=device_id,
                usuario_id=usuario_id,
            )
            return await self._trazabilidad_repository.agregar(registro)

        # PostgreSQL mantiene pg_advisory_xact_lock hasta commit. Combinarlo
        # con lock de proceso causa inversión: sesión A necesita lock proceso
        # para su segundo hash mientras B lo retiene esperando lock PostgreSQL
        # de A. SQLite no tiene advisory lock, por eso conserva este candado.
        session = getattr(self._trazabilidad_repository, "_session", None)
        bind = getattr(session, "bind", None)
        if bind is not None and bind.dialect.name == "postgresql":
            return await registrar()
        async with _CANDADO_CADENA:
            return await registrar()
