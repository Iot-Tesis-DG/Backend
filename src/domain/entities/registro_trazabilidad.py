from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.domain.value_objects.hash_encadenado import HashEncadenado, timestamp_canonico


@dataclass(slots=True)
class RegistroTrazabilidad:
    """Registro con hash SHA-256 encadenado que garantiza integridad verificable."""

    tipo_evento: str
    payload: dict
    timestamp: datetime
    hash_encadenado: HashEncadenado
    id: UUID | None = None
    device_id: str | None = None
    usuario_id: UUID | None = None

    @property
    def previous_hash(self) -> str:
        return self.hash_encadenado.previous_hash

    @property
    def hash_actual(self) -> str:
        return self.hash_encadenado.hash_actual

    def verificar_integridad(self) -> bool:
        return self.hash_encadenado.verificar(timestamp_canonico(self.timestamp), self.payload)
