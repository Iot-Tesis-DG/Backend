import hashlib
import json
from dataclasses import dataclass

GENESIS_HASH = "0" * 64


@dataclass(frozen=True, slots=True)
class HashEncadenado:
    """Vincula un registro de trazabilidad con el hash del registro anterior."""

    previous_hash: str
    hash_actual: str

    @staticmethod
    def calcular_hash(previous_hash: str, timestamp: str, payload: dict) -> str:
        contenido = previous_hash + timestamp + json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(contenido.encode("utf-8")).hexdigest()

    @classmethod
    def encadenar(cls, previous_hash: str, timestamp: str, payload: dict) -> "HashEncadenado":
        hash_actual = cls.calcular_hash(previous_hash, timestamp, payload)
        return cls(previous_hash=previous_hash, hash_actual=hash_actual)

    def verificar(self, timestamp: str, payload: dict) -> bool:
        return self.hash_actual == self.calcular_hash(self.previous_hash, timestamp, payload)
