from src.domain.value_objects.hash_encadenado import GENESIS_HASH, HashEncadenado


def test_encadenar_produce_hash_determinista():
    payload = {"temperatura": 4.2}
    a = HashEncadenado.encadenar(GENESIS_HASH, "2026-01-01T00:00:00+00:00", payload)
    b = HashEncadenado.encadenar(GENESIS_HASH, "2026-01-01T00:00:00+00:00", payload)
    assert a.hash_actual == b.hash_actual
    assert len(a.hash_actual) == 64


def test_hash_cambia_si_cambia_el_payload():
    a = HashEncadenado.encadenar(GENESIS_HASH, "2026-01-01T00:00:00+00:00", {"temperatura": 4.2})
    b = HashEncadenado.encadenar(GENESIS_HASH, "2026-01-01T00:00:00+00:00", {"temperatura": 4.3})
    assert a.hash_actual != b.hash_actual


def test_hash_cambia_si_cambia_previous_hash():
    payload = {"temperatura": 4.2}
    a = HashEncadenado.encadenar(GENESIS_HASH, "2026-01-01T00:00:00+00:00", payload)
    b = HashEncadenado.encadenar(a.hash_actual, "2026-01-01T00:00:00+00:00", payload)
    assert a.hash_actual != b.hash_actual


def test_verificar_detecta_alteracion_del_payload():
    registro = HashEncadenado.encadenar(GENESIS_HASH, "2026-01-01T00:00:00+00:00", {"temperatura": 4.2})
    assert registro.verificar("2026-01-01T00:00:00+00:00", {"temperatura": 4.2}) is True
    assert registro.verificar("2026-01-01T00:00:00+00:00", {"temperatura": 999.0}) is False


def test_orden_de_claves_en_payload_no_afecta_el_hash():
    a = HashEncadenado.encadenar(GENESIS_HASH, "t", {"a": 1, "b": 2})
    b = HashEncadenado.encadenar(GENESIS_HASH, "t", {"b": 2, "a": 1})
    assert a.hash_actual == b.hash_actual
