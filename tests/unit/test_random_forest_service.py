import pytest

from src.domain.value_objects.nivel_riesgo import NivelRiesgo
from src.infrastructure.ai.features import FeaturesRiesgoTermico
from src.infrastructure.ai.random_forest_service import RandomForestRiesgoService


@pytest.fixture(scope="module")
def servicio() -> RandomForestRiesgoService:
    return RandomForestRiesgoService()


def test_modelo_entrenado_esta_disponible(servicio):
    assert servicio.modelo_disponible is True


def test_lectura_estable_clasifica_como_normal(servicio):
    features = FeaturesRiesgoTermico(
        temperatura_ambiental=6.0,
        humedad_ambiental=50.0,
        temperatura_interna=5.0,
        diferencia_sensores=1.0,
        duracion_fuera_rango=0.0,
        frecuencia_desviaciones=0.0,
        tendencia_termica=0.0,
        apertura_refrigerador=False,
        hora_evento=12,
        estado_conectividad_online=True,
    )
    assert servicio.predecir(features) == NivelRiesgo.NORMAL


def test_excursion_prolongada_clasifica_como_critica(servicio):
    features = FeaturesRiesgoTermico(
        temperatura_ambiental=18.0,
        humedad_ambiental=60.0,
        temperatura_interna=15.0,
        diferencia_sensores=3.0,
        duracion_fuera_rango=90.0,
        frecuencia_desviaciones=5.0,
        tendencia_termica=2.5,
        apertura_refrigerador=True,
        hora_evento=3,
        estado_conectividad_online=True,
    )
    assert servicio.predecir(features) == NivelRiesgo.EXCURSION_CRITICA


def test_servicio_sin_modelo_entrenado_usa_regla_como_fallback(tmp_path):
    servicio_sin_modelo = RandomForestRiesgoService(model_path=tmp_path / "no_existe.pkl")
    assert servicio_sin_modelo.modelo_disponible is False

    features = FeaturesRiesgoTermico(
        temperatura_ambiental=6.0,
        humedad_ambiental=50.0,
        temperatura_interna=5.0,
        diferencia_sensores=1.0,
        duracion_fuera_rango=0.0,
        frecuencia_desviaciones=0.0,
        tendencia_termica=0.0,
        apertura_refrigerador=False,
        hora_evento=12,
        estado_conectividad_online=True,
    )
    assert servicio_sin_modelo.predecir(features) == NivelRiesgo.NORMAL


# ── Inferencia con evidencia (confianza + origen) ────────────────


def test_inferir_devuelve_confianza_y_origen_modelo(servicio):
    features = FeaturesRiesgoTermico(
        temperatura_ambiental=6.0,
        humedad_ambiental=50.0,
        temperatura_interna=5.0,
        diferencia_sensores=1.0,
        duracion_fuera_rango=0.0,
        frecuencia_desviaciones=0.0,
        tendencia_termica=0.0,
        apertura_refrigerador=False,
        hora_evento=12,
        estado_conectividad_online=True,
    )
    resultado = servicio.inferir(features)
    assert resultado.nivel == NivelRiesgo.NORMAL
    assert resultado.confianza is not None
    assert 0.0 <= resultado.confianza <= 1.0
    assert resultado.origen == "random_forest"
    assert resultado.estado_inferencia == "completada"


def test_fallback_sin_modelo_reporta_origen_regla(tmp_path):
    servicio_sin_modelo = RandomForestRiesgoService(model_path=tmp_path / "no_existe.pkl")
    features = FeaturesRiesgoTermico(
        temperatura_ambiental=6.0,
        humedad_ambiental=50.0,
        temperatura_interna=5.0,
        diferencia_sensores=1.0,
        duracion_fuera_rango=0.0,
        frecuencia_desviaciones=0.0,
        tendencia_termica=0.0,
        apertura_refrigerador=False,
        hora_evento=12,
        estado_conectividad_online=True,
    )
    resultado = servicio_sin_modelo.inferir(features)
    assert resultado.origen == "salvaguarda_determinista"
    assert resultado.confianza is None
    assert resultado.estado_inferencia == "modelo_no_disponible"


class _ModeloQueSiempreDiceNormal:
    """Doble de prueba: simula un falso negativo del bosque."""

    classes_ = ["excursion_critica", "normal", "riesgo_preventivo"]

    def predict_proba(self, _x):
        import numpy as np

        return np.array([[0.01, 0.98, 0.01]])


def test_salvaguarda_impide_que_el_modelo_rebaje_una_excursion(tmp_path):
    servicio = RandomForestRiesgoService(model_path=tmp_path / "no_existe.pkl")
    servicio._modelo = _ModeloQueSiempreDiceNormal()

    # 15 °C fuera de rango durante 90 min: la regla BPA exige excursión crítica.
    features = FeaturesRiesgoTermico(
        temperatura_ambiental=18.0,
        humedad_ambiental=60.0,
        temperatura_interna=15.0,
        diferencia_sensores=3.0,
        duracion_fuera_rango=90.0,
        frecuencia_desviaciones=5.0,
        tendencia_termica=2.5,
        apertura_refrigerador=True,
        hora_evento=3,
        estado_conectividad_online=True,
    )
    resultado = servicio.inferir(features)
    assert resultado.nivel == NivelRiesgo.EXCURSION_CRITICA
    assert resultado.origen == "salvaguarda_determinista"
    assert resultado.estado_inferencia == "completada"


def test_metadata_del_artefacto_v3_disponible(servicio):
    """El artefacto oficial es el v3 reproducible (AIV-01/AIV-06 corregidos:
    escenario_id determinista, model_hash sin circularidad de auto-referencia
    — ver audit-output/backend/ai-corrections/03_model_artifact_v3.md). v1 y
    v2 se conservan como evidencia histórica."""
    assert servicio.metadata is not None
    assert servicio.metadata["model_version"] == "3.0.0-reproducible"
    assert servicio.metadata["dataset_hash"], "El dataset_hash debe estar presente (RNF-04 auditable)"
    assert servicio.metadata["model_hash"], "El model_hash debe estar presente (RNF-04 auditable)"
    assert servicio.metadata["particion"], "La estrategia de partición debe quedar documentada"
    metricas = servicio.metricas_entrenamiento()
    assert metricas is not None
    assert metricas["f1_weighted"] >= 0.85
    assert metricas["rnf04"]["cumplido"] is True
