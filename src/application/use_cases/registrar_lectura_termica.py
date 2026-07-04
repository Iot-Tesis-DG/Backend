from src.domain.entities.lectura_termica import LecturaTermica
from src.domain.exceptions import LecturaInvalidaError
from src.domain.repositories.i_alerta_repository import IAlertaRepository
from src.domain.repositories.i_lectura_repository import ILecturaRepository
from src.domain.repositories.i_trazabilidad_repository import ITrazabilidadRepository
from src.domain.value_objects.nivel_riesgo import NivelRiesgo
from src.application.use_cases.clasificar_riesgo_termico import ClasificarRiesgoTermicoUseCase
from src.application.use_cases.generar_alerta import GenerarAlertaUseCase
from src.application.use_cases.registrar_hash_encadenado import RegistrarHashEncadenadoUseCase


class RegistrarLecturaTermicaUseCase:
    """Orquesta el pipeline completo de una lectura entrante (ver README sección 15):
    validar -> persistir -> clasificar riesgo -> generar alerta -> trazabilidad."""

    def __init__(
        self,
        lectura_repository: ILecturaRepository,
        alerta_repository: IAlertaRepository,
        trazabilidad_repository: ITrazabilidadRepository,
        clasificar_riesgo_use_case: ClasificarRiesgoTermicoUseCase,
    ) -> None:
        self._lectura_repository = lectura_repository
        self._generar_alerta = GenerarAlertaUseCase(alerta_repository)
        self._registrar_hash = RegistrarHashEncadenadoUseCase(trazabilidad_repository)
        self._clasificar_riesgo = clasificar_riesgo_use_case

    async def execute(self, lectura: LecturaTermica) -> LecturaTermica:
        if not lectura.es_lectura_valida():
            raise LecturaInvalidaError(
                f"Lectura fuera de rango físico plausible para device {lectura.device_id}"
            )

        historial = await self._lectura_repository.listar_recientes_por_device(
            lectura.device_id, limite=20
        )
        lectura.nivel_riesgo = self._clasificar_riesgo.execute(lectura, historial)

        lectura_guardada = await self._lectura_repository.agregar(lectura)

        await self._registrar_hash.execute(
            tipo_evento="LECTURA_TERMICA",
            payload={
                "device_id": lectura_guardada.device_id,
                "temperatura_ambiental": lectura_guardada.temperatura_ambiental,
                "humedad_ambiental": lectura_guardada.humedad_ambiental,
                "temperatura_interna": lectura_guardada.temperatura_interna,
                "apertura_refrigerador": lectura_guardada.apertura_refrigerador,
                "nivel_riesgo": lectura_guardada.nivel_riesgo.value,
            },
            device_id=lectura_guardada.device_id,
            timestamp=lectura_guardada.timestamp,
        )

        if lectura_guardada.nivel_riesgo != NivelRiesgo.NORMAL and lectura_guardada.id is not None:
            alerta = await self._generar_alerta.execute(
                reading_id=lectura_guardada.id,
                device_id=lectura_guardada.device_id,
                nivel_riesgo=lectura_guardada.nivel_riesgo,
            )
            if alerta is not None:
                await self._registrar_hash.execute(
                    tipo_evento="ALERTA_TERMICA",
                    payload={
                        "reading_id": str(lectura_guardada.id),
                        "device_id": lectura_guardada.device_id,
                        "nivel_riesgo": lectura_guardada.nivel_riesgo.value,
                        "mensaje": alerta.mensaje,
                    },
                    device_id=lectura_guardada.device_id,
                )

        return lectura_guardada
