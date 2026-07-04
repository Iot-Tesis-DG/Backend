from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(slots=True)
class AccionCorrectiva:
    alert_id: UUID
    usuario_id: UUID
    descripcion: str
    id: UUID | None = None
    created_at: datetime | None = None
