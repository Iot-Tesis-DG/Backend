"""Genera un dataset sintético consistente con la regla térmica base (2 C-8 C) y
entrena el clasificador Random Forest de riesgo térmico.

Uso: python -m src.infrastructure.ai.train_model
"""

import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split

from src.infrastructure.ai.features import FEATURE_NAMES, FeaturesRiesgoTermico
from src.infrastructure.ai.reglas_riesgo import clasificar_por_regla

MODELS_DIR = Path(__file__).parent / "models"
MODEL_PATH = MODELS_DIR / "random_forest_termico.pkl"
METRICS_PATH = MODELS_DIR / "training_metrics.json"

RANDOM_STATE = 42
N_SAMPLES = 6000


def generar_dataset(n_samples: int, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    filas: list[list[float]] = []
    etiquetas: list[str] = []

    for _ in range(n_samples):
        temperatura_interna = rng.uniform(-5.0, 15.0)
        temperatura_ambiental = temperatura_interna + rng.normal(2.0, 1.5)
        humedad_ambiental = float(np.clip(rng.normal(55.0, 15.0), 0.0, 100.0))
        diferencia_sensores = temperatura_ambiental - temperatura_interna
        duracion_fuera_rango = float(np.clip(rng.exponential(8.0), 0.0, 180.0))
        frecuencia_desviaciones = float(rng.poisson(1.2))
        tendencia_termica = float(rng.normal(0.0, 1.2))
        apertura_refrigerador = bool(rng.random() < 0.15)
        hora_evento = int(rng.integers(0, 24))
        estado_conectividad_online = bool(rng.random() < 0.92)

        features = FeaturesRiesgoTermico(
            temperatura_ambiental=temperatura_ambiental,
            humedad_ambiental=humedad_ambiental,
            temperatura_interna=temperatura_interna,
            diferencia_sensores=diferencia_sensores,
            duracion_fuera_rango=duracion_fuera_rango,
            frecuencia_desviaciones=frecuencia_desviaciones,
            tendencia_termica=tendencia_termica,
            apertura_refrigerador=apertura_refrigerador,
            hora_evento=hora_evento,
            estado_conectividad_online=estado_conectividad_online,
        )
        etiqueta = clasificar_por_regla(features)

        filas.append(features.to_array())
        etiquetas.append(etiqueta.value)

    return np.array(filas), np.array(etiquetas)


def entrenar() -> dict:
    rng = np.random.default_rng(RANDOM_STATE)
    x, y = generar_dataset(N_SAMPLES, rng)
    x_train, x_test, y_train, y_test = train_test_split(
        x, y, test_size=0.2, random_state=RANDOM_STATE, stratify=y
    )

    modelo = RandomForestClassifier(
        n_estimators=200,
        max_depth=12,
        min_samples_leaf=3,
        class_weight="balanced",
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    modelo.fit(x_train, y_train)

    y_pred = modelo.predict(x_test)
    reporte = classification_report(y_test, y_pred, output_dict=True, zero_division=0)
    matriz = confusion_matrix(y_test, y_pred, labels=modelo.classes_).tolist()
    importancias = dict(zip(FEATURE_NAMES, modelo.feature_importances_.tolist(), strict=True))

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(modelo, MODEL_PATH)

    metricas = {
        "n_samples": N_SAMPLES,
        "classes": modelo.classes_.tolist(),
        "classification_report": reporte,
        "confusion_matrix": matriz,
        "feature_importances": importancias,
        "f1_weighted": reporte["weighted avg"]["f1-score"],
    }
    METRICS_PATH.write_text(json.dumps(metricas, indent=2, ensure_ascii=False))
    return metricas


if __name__ == "__main__":
    resultado = entrenar()
    print(f"Modelo guardado en {MODEL_PATH}")
    print(f"F1-score ponderado: {resultado['f1_weighted']:.4f}")
