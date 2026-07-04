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
