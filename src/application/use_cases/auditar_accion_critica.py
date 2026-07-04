from uuid import UUID

from src.domain.repositories.i_audit_log_repository import IAuditLogRepository


class AuditarAccionCriticaUseCase:
    """RF-16: registra en audit_logs toda acción crítica ejecutada por un usuario autenticado."""

    def __init__(self, audit_log_repository: IAuditLogRepository) -> None:
        self._audit_log_repository = audit_log_repository

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
