from src.domain.value_objects.nivel_riesgo import NivelRiesgo
from src.domain.value_objects.rango_termico import RANGO_TERMICO_BPA
from src.infrastructure.ai.features import FeaturesRiesgoTermico

DURACION_CRITICA_MINUTOS = 30.0
DURACION_PREVENTIVA_MINUTOS = 10.0
TENDENCIA_CRITICA = 1.5
MARGEN_PREVENTIVO_C = 1.0


def clasificar_por_regla(features: FeaturesRiesgoTermico) -> NivelRiesgo:
    """Regla térmica base (2 C - 8 C) usada para generar el dataset sintético de
    entrenamiento y como red de seguridad de consistencia (ver README sección 7)."""
    temp = features.temperatura_interna
    fuera_de_rango = not RANGO_TERMICO_BPA.contiene(temp)

    if fuera_de_rango and (
        features.duracion_fuera_rango >= DURACION_CRITICA_MINUTOS
        or RANGO_TERMICO_BPA.distancia_al_limite(temp) >= MARGEN_PREVENTIVO_C * 2
    ):
        return NivelRiesgo.EXCURSION_CRITICA

    if fuera_de_rango:
        return NivelRiesgo.RIESGO_PREVENTIVO

    distancia = RANGO_TERMICO_BPA.distancia_al_limite(temp)
    if (
        distancia <= MARGEN_PREVENTIVO_C
        or features.duracion_fuera_rango >= DURACION_PREVENTIVA_MINUTOS
        or abs(features.tendencia_termica) >= TENDENCIA_CRITICA
        or features.frecuencia_desviaciones >= 3
    ):
        return NivelRiesgo.RIESGO_PREVENTIVO

    return NivelRiesgo.NORMAL
