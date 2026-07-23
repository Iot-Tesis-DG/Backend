from src.domain.entities.lectura_termica import LecturaTermica
from src.domain.exceptions import DispositivoNoAutorizadoError, LecturaInvalidaError
from src.domain.repositories.i_alerta_repository import IAlertaRepository
from src.domain.repositories.i_device_repository import IDeviceRepository
from src.domain.repositories.i_lectura_repository import ILecturaRepository
from src.domain.repositories.i_trazabilidad_repository import ITrazabilidadRepository
from src.application.use_cases.clasificar_riesgo_termico import ClasificarRiesgoTermicoUseCase
from src.application.use_cases.generar_alerta import GenerarAlertaUseCase
from src.application.use_cases.registrar_hash_encadenado import RegistrarHashEncadenadoUseCase


class RegistrarLecturaTermicaUseCase:
    """Orquesta el pipeline completo de una lectura entrante (ver README sección 15):
    autorizar dispositivo -> validar -> clasificar riesgo -> persistir ->
    generar alerta -> trazabilidad.

    Control de mínimo privilegio (RNF-05): en modo estricto solo los dispositivos
    provisionados en la tabla `devices` pueden registrar lecturas; un device_id
    desconocido se rechaza. En modo no estricto (desarrollo) el dispositivo se
    registra automáticamente, lo que además preserva la integridad referencial
    del FK `thermal_readings.device_id -> devices.id` en PostgreSQL.
    """

    def __init__(
        self,
        lectura_repository: ILecturaRepository,
        alerta_repository: IAlertaRepository,
        trazabilidad_repository: ITrazabilidadRepository,
        clasificar_riesgo_use_case: ClasificarRiesgoTermicoUseCase,
        device_repository: IDeviceRepository | None = None,
        registro_dispositivos_estricto: bool = False,
    ) -> None:
        self._lectura_repository = lectura_repository
        self._generar_alerta = GenerarAlertaUseCase(alerta_repository)
        self._registrar_hash = RegistrarHashEncadenadoUseCase(trazabilidad_repository)
        self._clasificar_riesgo = clasificar_riesgo_use_case
        self._device_repository = device_repository
        self._estricto = registro_dispositivos_estricto

    async def _autorizar_dispositivo(self, device_id: str) -> None:
        if self._device_repository is None:
            return
        if self._estricto:
            if not await self._device_repository.existe(device_id):
                raise DispositivoNoAutorizadoError(
                    f"El dispositivo '{device_id}' no está registrado; la lectura se rechaza."
                )
        else:
            await self._device_repository.obtener_o_crear(device_id)

    async def execute(self, lectura: LecturaTermica) -> LecturaTermica:
        await self._autorizar_dispositivo(lectura.device_id)

        if not lectura.es_lectura_valida():
            raise LecturaInvalidaError(
                f"Lectura fuera de rango físico plausible para device {lectura.device_id}"
            )

        # Deduplicación/idempotencia (corrige hallazgo B-04): un reenvío MQTT
        # (PUBACK perdido, QoS1) para el mismo dispositivo y el mismo instante
        # exacto no debe generar una lectura, alerta ni eslabón de hash duplicados.
        existente = await self._lectura_repository.obtener_por_device_y_timestamp(
            lectura.device_id, lectura.timestamp
        )
        if existente is not None:
            return existente

        historial = await self._lectura_repository.listar_recientes_por_device(
            lectura.device_id, limite=20
        )
        clasificacion = self._clasificar_riesgo.execute(lectura, historial)
        lectura.nivel_riesgo = clasificacion.nivel
        # Hallazgo AI-06: la versión del modelo y la confianza quedan en la
        # propia lectura, no solo en el payload de trazabilidad, para poder
        # auditar retroactivamente con qué modelo se clasificó cada registro.
        lectura.modelo_version = self._clasificar_riesgo.modelo_version
        # AIV-07: confianza_ia nunca es 0.0 como valor centinela cuando no
        # hubo inferencia real — se persiste NULL, distinguible de una
        # inferencia real con confianza matemática 0.
        lectura.confianza_ia = None if clasificacion.confianza is None else round(clasificacion.confianza, 4)
        lectura.origen_clasificacion = clasificacion.origen
        lectura.estado_inferencia = clasificacion.estado_inferencia
        lectura.motivo_no_inferencia = clasificacion.motivo_no_inferencia

        lectura_guardada = await self._lectura_repository.agregar(lectura)

        await self._registrar_hash.execute(
            tipo_evento="LECTURA_TERMICA",
            payload={
                "device_id": lectura_guardada.device_id,
                "temperatura_ambiental": lectura_guardada.temperatura_ambiental,
                "humedad_ambiental": lectura_guardada.humedad_ambiental,
                "temperatura_interna": lectura_guardada.temperatura_interna,
                "apertura_refrigerador": lectura_guardada.apertura_refrigerador,
                # None (sensor caído, hallazgo B-05) se serializa explícitamente
                # como tal, nunca como un nivel de riesgo inventado.
                "nivel_riesgo": lectura_guardada.nivel_riesgo.value
                if lectura_guardada.nivel_riesgo is not None
                else None,
                # Evidencia de la inferencia (RNF-04 / supervisión de la IA).
                "confianza_ia": lectura_guardada.confianza_ia,
                "origen_clasificacion": clasificacion.origen,
                "modelo_version": lectura_guardada.modelo_version,
                "estado_inferencia": clasificacion.estado_inferencia,
                "motivo_no_inferencia": clasificacion.motivo_no_inferencia,
            },
            device_id=lectura_guardada.device_id,
            timestamp=lectura_guardada.timestamp,
        )

        # AIV-02: se evalúa el episodio de alerta para TODA lectura
        # clasificada (incluida "normal", que puede cerrar un episodio
        # abierto como evento de recuperación) — no solo para las críticas.
        # Una lectura sin dato de sensor (nivel_riesgo=None) no se evalúa:
        # no hay evidencia de que el riesgo se haya resuelto.
        if lectura_guardada.nivel_riesgo is not None and lectura_guardada.id is not None:
            alerta = await self._generar_alerta.execute(
                reading_id=lectura_guardada.id,
                device_id=lectura_guardada.device_id,
                nivel_riesgo=lectura_guardada.nivel_riesgo,
                timestamp=lectura_guardada.timestamp,
            )
            if alerta is not None:
                await self._registrar_hash.execute(
                    tipo_evento="ALERTA_TERMICA",
                    payload={
                        "reading_id": str(lectura_guardada.id),
                        "device_id": lectura_guardada.device_id,
                        "nivel_riesgo": lectura_guardada.nivel_riesgo.value,
                        "mensaje": alerta.mensaje,
                        "modelo_version": lectura_guardada.modelo_version,
                        "confianza_ia": lectura_guardada.confianza_ia,
                        "episodio_abierto": alerta.episodio_abierto,
                    },
                    device_id=lectura_guardada.device_id,
                )

        return lectura_guardada
