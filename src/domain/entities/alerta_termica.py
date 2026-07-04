from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.domain.value_objects.nivel_riesgo import NivelRiesgo


@dataclass(slots=True)
class AlertaTermica:
    """Alerta generada cuando una lectura clasifica como riesgo_preventivo o excursion_critica."""

    reading_id: UUID
    device_id: str
    nivel_riesgo: NivelRiesgo
    mensaje: str
    id: UUID | None = None
    revisada: bool = False
    revisada_por: UUID | None = None
    created_at: datetime | None = None

    def marcar_revisada(self, usuario_id: UUID) -> None:
        self.revisada = True
        self.revisada_por = usuario_id
