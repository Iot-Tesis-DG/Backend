from datetime import datetime, timezone

from tests.conftest import auth_header


def _payload_excursion_critica(device_id: str = "FARM-ALERTA-01") -> dict:
    return {
        "device_id": device_id,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "temperatura_ambiental": 20.0,
        "humedad_ambiental": 60.0,
        "temperatura_interna": 18.0,
        "apertura_refrigerador": True,
        "estado_conectividad": "online",
    }


async def test_lectura_critica_genera_alerta_automaticamente(client, token_tecnico):
    client.post("/api/lecturas", json=_payload_excursion_critica(), headers=auth_header(token_tecnico))

    response = client.get(
        "/api/alertas", params={"device_id": "FARM-ALERTA-01"}, headers=auth_header(token_tecnico)
    )

    assert response.status_code == 200
    alertas = response.json()
    assert len(alertas) == 1
    assert alertas[0]["nivel_riesgo"] == "excursion_critica"
    assert alertas[0]["revisada"] is False


async def test_lectura_normal_no_genera_alerta(client, token_tecnico):
    client.post(
        "/api/lecturas",
        json={
            "device_id": "FARM-SIN-ALERTA",
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "temperatura_ambiental": 6.0,
            "humedad_ambiental": 55.0,
            "temperatura_interna": 5.0,
            "apertura_refrigerador": False,
            "estado_conectividad": "online",
        },
        headers=auth_header(token_tecnico),
    )

    response = client.get(
        "/api/alertas", params={"device_id": "FARM-SIN-ALERTA"}, headers=auth_header(token_tecnico)
    )
    assert response.json() == []


async def test_farmaceutico_puede_revisar_alerta(client, token_tecnico, token_farmaceutico):
    client.post(
        "/api/lecturas", json=_payload_excursion_critica("FARM-REVISAR"), headers=auth_header(token_tecnico)
    )
    alerta = client.get(
        "/api/alertas", params={"device_id": "FARM-REVISAR"}, headers=auth_header(token_tecnico)
    ).json()[0]

    response = client.patch(
        f"/api/alertas/{alerta['id']}/revisar", headers=auth_header(token_farmaceutico)
    )

    assert response.status_code == 200
    assert response.json()["revisada"] is True


async def test_tecnico_no_puede_revisar_alerta(client, token_tecnico):
    client.post(
        "/api/lecturas",
        json=_payload_excursion_critica("FARM-REVISAR-TECNICO"),
        headers=auth_header(token_tecnico),
    )
    alerta = client.get(
        "/api/alertas", params={"device_id": "FARM-REVISAR-TECNICO"}, headers=auth_header(token_tecnico)
    ).json()[0]

    response = client.patch(f"/api/alertas/{alerta['id']}/revisar", headers=auth_header(token_tecnico))
    assert response.status_code == 403


async def test_registrar_accion_correctiva_sobre_alerta(client, token_tecnico):
    client.post(
        "/api/lecturas",
        json=_payload_excursion_critica("FARM-ACCION"),
        headers=auth_header(token_tecnico),
    )
    alerta = client.get(
        "/api/alertas", params={"device_id": "FARM-ACCION"}, headers=auth_header(token_tecnico)
    ).json()[0]

    response = client.post(
        f"/api/alertas/{alerta['id']}/acciones-correctivas",
        json={"descripcion": "Se trasladó el medicamento a refrigerador de respaldo."},
        headers=auth_header(token_tecnico),
    )

    assert response.status_code == 201
    assert response.json()["descripcion"] == "Se trasladó el medicamento a refrigerador de respaldo."


async def test_accion_correctiva_sobre_alerta_inexistente_devuelve_404(client, token_tecnico):
    response = client.post(
        "/api/alertas/00000000-0000-0000-0000-000000000000/acciones-correctivas",
        json={"descripcion": "No debería aplicar"},
        headers=auth_header(token_tecnico),
    )
    assert response.status_code == 404
