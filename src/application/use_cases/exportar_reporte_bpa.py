from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.domain.entities.alerta_termica import AlertaTermica
from src.domain.entities.lectura_termica import LecturaTermica
from src.domain.entities.registro_trazabilidad import RegistroTrazabilidad
from src.domain.repositories.i_alerta_repository import IAlertaRepository
from src.domain.repositories.i_lectura_repository import ILecturaRepository
from src.domain.repositories.i_reporte_repository import IReporteRepository
from src.domain.repositories.i_trazabilidad_repository import ITrazabilidadRepository


@dataclass(frozen=True, slots=True)
class ReporteBPA:
    device_id: str | None
    fecha_desde: datetime
    fecha_hasta: datetime
    lecturas: list[LecturaTermica]
    alertas: list[AlertaTermica]
    registros_trazabilidad: list[RegistroTrazabilidad]


class ExportarReporteBPAUseCase:
    """RF-13: reporte exportable con soporte documental de Buenas Prácticas de
    Almacenamiento (historial térmico, alertas y trazabilidad del periodo)."""

    def __init__(
        self,
        lectura_repository: ILecturaRepository,
        alerta_repository: IAlertaRepository,
        trazabilidad_repository: ITrazabilidadRepository,
        reporte_repository: IReporteRepository,
    ) -> None:
        self._lectura_repository = lectura_repository
        self._alerta_repository = alerta_repository
        self._trazabilidad_repository = trazabilidad_repository
        self._reporte_repository = reporte_repository

    async def execute(
        self,
        usuario_id: UUID,
        fecha_desde: datetime,
        fecha_hasta: datetime,
        device_id: str | None = None,
    ) -> ReporteBPA:
        lecturas = await self._lectura_repository.listar(
            device_id=device_id, desde=fecha_desde, hasta=fecha_hasta, limite=10_000
        )
        alertas = await self._alerta_repository.listar(device_id=device_id, limite=10_000)
        trazabilidad = await self._trazabilidad_repository.listar(device_id=device_id, limite=10_000)

        await self._reporte_repository.registrar_exportacion(
            usuario_id=usuario_id,
            tipo_reporte="BPA",
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
        )

        return ReporteBPA(
            device_id=device_id,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            lecturas=lecturas,
            alertas=alertas,
            registros_trazabilidad=trazabilidad,
        )
