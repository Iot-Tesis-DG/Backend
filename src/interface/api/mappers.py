from src.domain.entities.alerta_termica import AlertaTermica
from src.domain.entities.lectura_termica import LecturaTermica
from src.domain.entities.registro_trazabilidad import RegistroTrazabilidad
from src.interface.api.schemas import AlertaResponse, LecturaResponse, TrazabilidadResponse


def lectura_to_response(lectura: LecturaTermica) -> LecturaResponse:
    return LecturaResponse(
        id=lectura.id,
        device_id=lectura.device_id,
        timestamp=lectura.timestamp,
        temperatura_ambiental=lectura.temperatura_ambiental,
        humedad_ambiental=lectura.humedad_ambiental,
        temperatura_interna=lectura.temperatura_interna,
        apertura_refrigerador=lectura.apertura_refrigerador,
        estado_conectividad=lectura.estado_conectividad,
        nivel_riesgo=lectura.nivel_riesgo,
    )


def alerta_to_response(alerta: AlertaTermica) -> AlertaResponse:
    return AlertaResponse(
        id=alerta.id,
        reading_id=alerta.reading_id,
        device_id=alerta.device_id,
        nivel_riesgo=alerta.nivel_riesgo,
        mensaje=alerta.mensaje,
        revisada=alerta.revisada,
        revisada_por=alerta.revisada_por,
        created_at=alerta.created_at,
    )


def trazabilidad_to_response(registro: RegistroTrazabilidad) -> TrazabilidadResponse:
    return TrazabilidadResponse(
        id=registro.id,
        tipo_evento=registro.tipo_evento,
        device_id=registro.device_id,
        usuario_id=registro.usuario_id,
        payload=registro.payload,
        timestamp=registro.timestamp,
        previous_hash=registro.previous_hash,
        hash_actual=registro.hash_actual,
    )
