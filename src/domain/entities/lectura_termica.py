from dataclasses import dataclass
from datetime import datetime
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

    def diferencia_sensores(self) -> float:
        if self.temperatura_ambiental is None or self.temperatura_interna is None:
            return 0.0
        return self.temperatura_ambiental - self.temperatura_interna

    def es_lectura_valida(self) -> bool:
        """Validación básica de rango plausible antes de persistir/clasificar."""
        if self.temperatura_ambiental is not None and not (-40.0 <= self.temperatura_ambiental <= 125.0):
            return False
        if self.temperatura_interna is not None and not (-55.0 <= self.temperatura_interna <= 125.0):
            return False
        if self.humedad_ambiental is not None and not (0.0 <= self.humedad_ambiental <= 100.0):
            return False
        return True
