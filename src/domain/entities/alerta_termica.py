from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.domain.value_objects.nivel_riesgo import NivelRiesgo


@dataclass(slots=True)
class AlertaTermica:
    """Alerta generada cuando una lectura clasifica como riesgo_preventivo o
    excursion_critica. Corrige AIV-02: representa un EPISODIO (no una lectura
    aislada) — mientras el riesgo se mantiene, la misma alerta se actualiza en
    vez de crearse una nueva por cada lectura ("tormenta de alertas")."""

    reading_id: UUID
    device_id: str
    nivel_riesgo: NivelRiesgo
    mensaje: str
    id: UUID | None = None
    revisada: bool = False
    revisada_por: UUID | None = None
    created_at: datetime | None = None
    # AIV-02 — control de episodio.
    episodio_abierto: bool = True
    lectura_inicial_id: UUID | None = None
    lectura_mas_reciente_id: UUID | None = None
    ultima_actualizacion: datetime | None = None
    cerrada_en: datetime | None = None

    def marcar_revisada(self, usuario_id: UUID) -> None:
        self.revisada = True
        self.revisada_por = usuario_id

    def registrar_lectura(self, reading_id: UUID, timestamp: datetime) -> None:
        """El episodio sigue activo: se actualiza la lectura más reciente y el
        timestamp, sin crear una fila nueva ni cambiar `reading_id` original
        (que sigue apuntando a la lectura que originó la alerta)."""
        self.lectura_mas_reciente_id = reading_id
        self.ultima_actualizacion = timestamp

    def cerrar(self, timestamp: datetime) -> None:
        """El riesgo volvió a NORMAL (evento de recuperación) o el episodio
        escaló/desescaló a otro nivel de riesgo distinto."""
        self.episodio_abierto = False
        self.cerrada_en = timestamp

    def reabrir(self, reading_id: UUID, timestamp: datetime) -> None:
        """Dentro de la ventana de cooldown, un episodio recién cerrado del
        mismo dispositivo y tipo de riesgo se reabre en vez de crear una
        alerta nueva (evita flapping de apertura/cierre inmediato)."""
        self.episodio_abierto = True
        self.cerrada_en = None
        self.lectura_mas_reciente_id = reading_id
        self.ultima_actualizacion = timestamp
