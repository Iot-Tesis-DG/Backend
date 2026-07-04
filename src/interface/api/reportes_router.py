from datetime import datetime

from fastapi import APIRouter, Depends, Request

from src.application.use_cases.auditar_accion_critica import AuditarAccionCriticaUseCase
from src.application.use_cases.exportar_reporte_bpa import ExportarReporteBPAUseCase
from src.domain.value_objects.rol import Rol
from src.infrastructure.database.repositories.alerta_repository import SQLAlchemyAlertaRepository
from src.infrastructure.database.repositories.audit_log_repository import SQLAlchemyAuditLogRepository
from src.infrastructure.database.repositories.lectura_repository import SQLAlchemyLecturaRepository
from src.infrastructure.database.repositories.reporte_repository import SQLAlchemyReporteRepository
from src.infrastructure.database.repositories.trazabilidad_repository import (
    SQLAlchemyTrazabilidadRepository,
)
from src.interface.api.deps import DbSessionDep, require_roles
from src.interface.api.mappers import alerta_to_response, lectura_to_response, trazabilidad_to_response
from src.interface.api.schemas import ReporteBPAResponse

router = APIRouter(prefix="/api/reportes", tags=["reportes"])


@router.get("/bpa", response_model=ReporteBPAResponse)
async def exportar_reporte_bpa(
    fecha_desde: datetime,
    fecha_hasta: datetime,
    session: DbSessionDep,
    request: Request,
    usuario=Depends(require_roles(Rol.FARMACEUTICO)),
    device_id: str | None = None,
) -> ReporteBPAResponse:
    lectura_repository = SQLAlchemyLecturaRepository(session)
    alerta_repository = SQLAlchemyAlertaRepository(session)
    trazabilidad_repository = SQLAlchemyTrazabilidadRepository(session)
    reporte_repository = SQLAlchemyReporteRepository(session)

    use_case = ExportarReporteBPAUseCase(
        lectura_repository, alerta_repository, trazabilidad_repository, reporte_repository
    )
    reporte = await use_case.execute(usuario.id, fecha_desde, fecha_hasta, device_id)

    auditoria_repository = SQLAlchemyAuditLogRepository(session)
    await AuditarAccionCriticaUseCase(auditoria_repository).execute(
        usuario_id=usuario.id,
        accion="EXPORTAR_REPORTE_BPA",
        recurso="reportes/bpa",
        detalle={
            "device_id": device_id,
            "fecha_desde": fecha_desde.isoformat(),
            "fecha_hasta": fecha_hasta.isoformat(),
        },
        ip_origen=request.client.host if request.client else None,
    )
    await session.commit()

    return ReporteBPAResponse(
        device_id=reporte.device_id,
        fecha_desde=reporte.fecha_desde,
        fecha_hasta=reporte.fecha_hasta,
        lecturas=[lectura_to_response(l) for l in reporte.lecturas],
        alertas=[alerta_to_response(a) for a in reporte.alertas],
        registros_trazabilidad=[trazabilidad_to_response(r) for r in reporte.registros_trazabilidad],
    )
