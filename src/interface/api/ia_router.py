from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.domain.value_objects.rol import Rol
from src.infrastructure.ai.features import FeaturesRiesgoTermico
from src.infrastructure.ai.random_forest_service import get_random_forest_service
from src.interface.api.deps import require_roles

router = APIRouter(prefix="/api/ia", tags=["ia"])


class ClasificacionRequest(BaseModel):
    """Vector de features para una clasificación de prueba (validación técnica)."""

    temperatura_ambiental: float = Field(ge=-40.0, le=125.0)
    humedad_ambiental: float = Field(ge=0.0, le=100.0)
    temperatura_interna: float = Field(ge=-55.0, le=125.0)
    diferencia_sensores: float
    duracion_fuera_rango: float = Field(ge=0.0, le=1440.0)
    frecuencia_desviaciones: float = Field(ge=0.0)
    tendencia_termica: float
    apertura_refrigerador: bool = False
    hora_evento: int = Field(ge=0, le=23)
    estado_conectividad_online: bool = True


class ClasificacionResponse(BaseModel):
    nivel_riesgo: str
    confianza: float
    origen: str


@router.get("/modelo")
async def obtener_metadata_modelo(
    _usuario=Depends(require_roles(Rol.FARMACEUTICO)),
) -> dict:
    """Evidencia del modelo Random Forest para la validación técnica (RNF-04):
    metadatos del artefacto y métricas de entrenamiento (accuracy, precision,
    recall, F1 por clase, matriz de confusión y validación cruzada)."""
    servicio = get_random_forest_service()
    metricas = servicio.metricas_entrenamiento()
    if not servicio.modelo_disponible or metricas is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El modelo Random Forest no está entrenado en este entorno.",
        )
    return {
        "modelo_disponible": True,
        "metadata": servicio.metadata,
        "metricas": metricas,
    }


@router.post("/clasificar", response_model=ClasificacionResponse)
async def clasificar_prueba(
    body: ClasificacionRequest,
    _usuario=Depends(require_roles(Rol.FARMACEUTICO)),
) -> ClasificacionResponse:
    """Clasificación bajo demanda para las pruebas E2E de la tesis (RF-08):
    permite verificar la respuesta del clasificador ante un vector arbitrario
    sin registrar lecturas ni generar alertas."""
    servicio = get_random_forest_service()
    resultado = servicio.inferir(FeaturesRiesgoTermico(**body.model_dump()))
    return ClasificacionResponse(
        nivel_riesgo=resultado.nivel.value,
        confianza=round(resultado.confianza, 4),
        origen=resultado.origen,
    )
