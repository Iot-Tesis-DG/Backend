from datetime import datetime, timezone
from uuid import UUID

from src.application.use_cases.registrar_hash_encadenado import RegistrarHashEncadenadoUseCase
from src.domain.repositories.i_audit_log_repository import IAuditLogRepository
from src.domain.repositories.i_trazabilidad_repository import ITrazabilidadRepository


class AuditarAccionCriticaUseCase:
    """RF-16: registra en audit_logs toda acción crítica ejecutada por un usuario autenticado.

    HU-42: audit_logs es la vista operativa de solo lectura, pero cada entrada
    se encadena TAMBIÉN a la misma cadena SHA-256 global (traceability_records)
    que usan las lecturas y alertas — no una cadena paralela sin justificación
    (Observación 7 del backlog de 51 HU). Si `trazabilidad_repository` no se
    provee, la entrada se registra igual en audit_logs pero sin encadenar
    (compatibilidad hacia atrás para pruebas que solo verifican audit_logs).
    """

    def __init__(
        self,
        audit_log_repository: IAuditLogRepository,
        trazabilidad_repository: ITrazabilidadRepository | None = None,
    ) -> None:
        self._audit_log_repository = audit_log_repository
        self._registrar_hash = (
            RegistrarHashEncadenadoUseCase(trazabilidad_repository)
            if trazabilidad_repository is not None
            else None
        )

    async def execute(
        self,
        usuario_id: UUID | None,
        accion: str,
        recurso: str,
        detalle: dict | None = None,
        ip_origen: str | None = None,
    ) -> None:
        await self._audit_log_repository.registrar(
            usuario_id=usuario_id,
            accion=accion,
            recurso=recurso,
            detalle=detalle or {},
            ip_origen=ip_origen,
        )
        if self._registrar_hash is not None:
            await self._registrar_hash.execute(
                tipo_evento="AUDIT_LOG",
                payload={
                    "accion": accion,
                    "recurso": recurso,
                    "detalle": detalle or {},
                    "ip_origen": ip_origen,
                },
                usuario_id=usuario_id,
                timestamp=datetime.now(tz=timezone.utc),
            )
