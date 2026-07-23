from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.application.use_cases.clasificar_riesgo_termico import ClasificarRiesgoTermicoUseCase
from src.application.use_cases.consultar_historial_termico import ConsultarHistorialTermicoUseCase
from src.application.use_cases.registrar_lectura_termica import RegistrarLecturaTermicaUseCase
from src.domain.entities.lectura_termica import LecturaTermica
from src.domain.exceptions import DispositivoNoAutorizadoError, LecturaInvalidaError
from src.domain.value_objects.rol import Rol
from src.infrastructure.ai.random_forest_service import get_random_forest_service
from src.infrastructure.database.repositories.alerta_repository import SQLAlchemyAlertaRepository
from src.infrastructure.database.repositories.device_repository import SQLAlchemyDeviceRepository
from src.infrastructure.database.repositories.lectura_repository import SQLAlchemyLecturaRepository
from src.infrastructure.database.repositories.trazabilidad_repository import (
    SQLAlchemyTrazabilidadRepository,
)
from src.interface.api.deps import DbSessionDep, SettingsDep, require_roles
from src.interface.api.mappers import lectura_to_response
from src.interface.api.schemas import LecturaIngestRequest, LecturaResponse

router = APIRouter(prefix="/api/lecturas", tags=["lecturas"])


@router.post("", response_model=LecturaResponse, status_code=status.HTTP_201_CREATED)
async def ingestar_lectura(
    body: LecturaIngestRequest,
    session: DbSessionDep,
    settings: SettingsDep,
    _usuario=Depends(require_roles(Rol.TECNICO, Rol.FARMACEUTICO)),
) -> LecturaResponse:
    lectura_repository = SQLAlchemyLecturaRepository(session)
    alerta_repository = SQLAlchemyAlertaRepository(session)
    trazabilidad_repository = SQLAlchemyTrazabilidadRepository(session)
    clasificar_use_case = ClasificarRiesgoTermicoUseCase(get_random_forest_service())

    use_case = RegistrarLecturaTermicaUseCase(
        lectura_repository,
        alerta_repository,
        trazabilidad_repository,
        clasificar_use_case,
        device_repository=SQLAlchemyDeviceRepository(session),
        registro_dispositivos_estricto=settings.device_registry_estricto,
    )
    lectura = LecturaTermica(
        device_id=body.device_id,
        timestamp=body.timestamp,
        temperatura_ambiental=body.temperatura_ambiental,
        humedad_ambiental=body.humedad_ambiental,
        temperatura_interna=body.temperatura_interna,
        apertura_refrigerador=body.apertura_refrigerador,
        estado_conectividad=body.estado_conectividad,
    )
    try:
        lectura_guardada = await use_case.execute(lectura)
    except DispositivoNoAutorizadoError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except LecturaInvalidaError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    await session.commit()
    return lectura_to_response(lectura_guardada)


@router.get("", response_model=list[LecturaResponse])
async def listar_historial(
    session: DbSessionDep,
    _usuario=Depends(require_roles(Rol.TECNICO, Rol.FARMACEUTICO)),
    device_id: str | None = None,
    nivel_riesgo: str | None = None,
    estado_conectividad: str | None = None,
    desde: datetime | None = None,
    hasta: datetime | None = None,
    limite: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[LecturaResponse]:
    lectura_repository = SQLAlchemyLecturaRepository(session)
    use_case = ConsultarHistorialTermicoUseCase(lectura_repository)
    lecturas = await use_case.execute(
        device_id=device_id,
        nivel_riesgo=nivel_riesgo,
        estado_conectividad=estado_conectividad,
        desde=desde,
        hasta=hasta,
        limite=limite,
        offset=offset,
    )
    return [lectura_to_response(lectura) for lectura in lecturas]


@router.get("/{lectura_id}", response_model=LecturaResponse)
async def obtener_lectura(
    lectura_id: UUID,
    session: DbSessionDep,
    _usuario=Depends(require_roles(Rol.TECNICO, Rol.FARMACEUTICO)),
) -> LecturaResponse:
    lectura_repository = SQLAlchemyLecturaRepository(session)
    lectura = await lectura_repository.obtener_por_id(lectura_id)
    if lectura is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lectura no encontrada")
    return lectura_to_response(lectura)
