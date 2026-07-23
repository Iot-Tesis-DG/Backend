from dataclasses import dataclass
from datetime import datetime
import math
from numbers import Real
from uuid import UUID

from src.domain.value_objects.nivel_riesgo import NivelRiesgo


@dataclass(slots=True)
class LecturaTermica:
    """Lectura térmica capturada por el nodo edge (ESP32 + SHT31 + DS18B20)."""

    device_id: str
    timestamp: datetime
    temperatura_ambiental: float | None
    humedad_ambiental: float | None
    temperatura_interna: float | None
    apertura_refrigerador: bool
    estado_conectividad: str
    id: UUID | None = None
    nivel_riesgo: NivelRiesgo | None = None
    payload: dict | None = None
    # Evidencia de la inferencia de IA (RNF-04, corrige hallazgo AI-06): con
    # qué versión de modelo, confianza y origen (modelo/regla/sin dato) se
    # clasificó esta lectura. None cuando aún no se clasificó.
    modelo_version: str | None = None
    confianza_ia: float | None = None
    origen_clasificacion: str | None = None
    # AIV-07: estado real de la inferencia (completada/omitida/fallida/
    # modelo_no_disponible) y motivo breve cuando no fue "completada" — nunca
    # contiene trazas de pila ni secretos, solo un código corto.
    estado_inferencia: str | None = None
    motivo_no_inferencia: str | None = None

    def diferencia_sensores(self) -> float:
        if self.temperatura_ambiental is None or self.temperatura_interna is None:
            return 0.0
        return self.temperatura_ambiental - self.temperatura_interna

    def es_lectura_valida(self) -> bool:
        """Validación básica de rango plausible antes de persistir/clasificar."""
        for valor, minimo, maximo in (
            (self.temperatura_ambiental, -40.0, 125.0),
            (self.temperatura_interna, -55.0, 125.0),
            (self.humedad_ambiental, 0.0, 100.0),
        ):
            if valor is not None and (
                not isinstance(valor, Real)
                or isinstance(valor, bool)
                or not math.isfinite(valor)
                or not minimo <= valor <= maximo
            ):
                return False
        return True
