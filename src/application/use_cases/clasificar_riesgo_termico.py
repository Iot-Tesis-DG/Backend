import numpy as np

from src.domain.entities.lectura_termica import LecturaTermica
from src.domain.value_objects.nivel_riesgo import NivelRiesgo
from src.domain.value_objects.rango_termico import RANGO_TERMICO_BPA
from src.infrastructure.ai.features import FeaturesRiesgoTermico
from src.infrastructure.ai.random_forest_service import RandomForestRiesgoService

UMBRAL_DESVIACION_C = 0.5


class ClasificarRiesgoTermicoUseCase:
    """Enriquece la lectura con features derivadas del historial y ejecuta el
    modelo Random Forest (ver README secciones 7 y 15)."""

    def __init__(self, ai_service: RandomForestRiesgoService) -> None:
        self._ai_service = ai_service

    def _construir_features(
        self, lectura: LecturaTermica, historial: list[LecturaTermica]
    ) -> FeaturesRiesgoTermico:
        temperatura_interna = lectura.temperatura_interna or 0.0

        historial_ordenado = sorted(historial, key=lambda l: l.timestamp)
        temperaturas_previas = [
            h.temperatura_interna for h in historial_ordenado if h.temperatura_interna is not None
        ]

        duracion_fuera_rango = 0.0
        if historial_ordenado:
            for h in reversed(historial_ordenado):
                if h.temperatura_interna is None or RANGO_TERMICO_BPA.contiene(h.temperatura_interna):
                    break
                delta = (lectura.timestamp - h.timestamp).total_seconds() / 60.0
                duracion_fuera_rango = max(duracion_fuera_rango, abs(delta))

        frecuencia_desviaciones = sum(
            1
            for t in temperaturas_previas
            if not RANGO_TERMICO_BPA.contiene(t)
        )

        tendencia_termica = 0.0
        if len(temperaturas_previas) >= 2:
            x = np.arange(len(temperaturas_previas), dtype=float)
            y = np.array(temperaturas_previas, dtype=float)
            pendiente, _ = np.polyfit(x, y, 1)
            tendencia_termica = float(pendiente)

        return FeaturesRiesgoTermico(
            temperatura_ambiental=lectura.temperatura_ambiental or 0.0,
            humedad_ambiental=lectura.humedad_ambiental or 0.0,
            temperatura_interna=temperatura_interna,
            diferencia_sensores=lectura.diferencia_sensores(),
            duracion_fuera_rango=duracion_fuera_rango,
            frecuencia_desviaciones=float(frecuencia_desviaciones),
            tendencia_termica=tendencia_termica,
            apertura_refrigerador=lectura.apertura_refrigerador,
            hora_evento=lectura.timestamp.hour,
            estado_conectividad_online=lectura.estado_conectividad == "online",
        )

    def execute(self, lectura: LecturaTermica, historial: list[LecturaTermica]) -> NivelRiesgo:
        features = self._construir_features(lectura, historial)
        return self._ai_service.predecir(features)
