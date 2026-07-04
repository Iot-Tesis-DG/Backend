from pathlib import Path
from threading import Lock

import joblib

from src.domain.value_objects.nivel_riesgo import NivelRiesgo
from src.infrastructure.ai.features import FeaturesRiesgoTermico
from src.infrastructure.ai.reglas_riesgo import clasificar_por_regla

DEFAULT_MODEL_PATH = Path(__file__).parent / "models" / "random_forest_termico.pkl"


class RandomForestRiesgoService:
    """Carga perezosa (lazy) del modelo joblib e inferencia de riesgo térmico.

    Si el modelo entrenado no está disponible (p. ej. entorno recién clonado sin
    ejecutar train_model.py), degrada de forma controlada a la regla térmica base
    en lugar de fallar el arranque del backend.
    """

    def __init__(self, model_path: Path | None = None) -> None:
        self._model_path = model_path or DEFAULT_MODEL_PATH
        self._modelo = None
        self._lock = Lock()

    def _cargar_modelo(self):
        if self._modelo is None:
            with self._lock:
                if self._modelo is None and self._model_path.exists():
                    self._modelo = joblib.load(self._model_path)
        return self._modelo

    @property
    def modelo_disponible(self) -> bool:
        return self._cargar_modelo() is not None

    def predecir(self, features: FeaturesRiesgoTermico) -> NivelRiesgo:
        modelo = self._cargar_modelo()
        if modelo is None:
            return clasificar_por_regla(features)
        prediccion = modelo.predict([features.to_array()])[0]
        return NivelRiesgo(prediccion)


_instancia: RandomForestRiesgoService | None = None


def get_random_forest_service() -> RandomForestRiesgoService:
    global _instancia
    if _instancia is None:
        _instancia = RandomForestRiesgoService()
    return _instancia
