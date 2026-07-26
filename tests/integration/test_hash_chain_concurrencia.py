"""Prueba concurrente del hallazgo B-01 (auditoría): confirma que N eslabones
de la cadena SHA-256 generados casi simultáneamente, desde sesiones de base de
datos independientes, no bifurcan la cadena — es decir, que el candado de
proceso (_CANDADO_CADENA) serializa correctamente la sección crítica
"leer último hash + insertar siguiente eslabón".
"""

import asyncio
from itertools import pairwise

from src.application.use_cases.registrar_hash_encadenado import RegistrarHashEncadenadoUseCase
from src.application.use_cases.verificar_integridad_registro import (
    VerificarIntegridadRegistroUseCase,
)
from src.infrastructure.database.repositories.trazabilidad_repository import (
    SQLAlchemyTrazabilidadRepository,
)

N_ESCRITURAS_CONCURRENTES = 20


async def _registrar_un_evento(db_session_factory, indice: int) -> None:
    async with db_session_factory() as session:
        repositorio = SQLAlchemyTrazabilidadRepository(session)
        use_case = RegistrarHashEncadenadoUseCase(repositorio)
        await use_case.execute(
            tipo_evento="LECTURA_TERMICA",
            payload={"indice": indice},
            device_id=f"FARM-{indice % 3}",
        )
        await session.commit()


async def test_escrituras_concurrentes_no_bifurcan_la_cadena(db_session_factory):
    await asyncio.gather(
        *[_registrar_un_evento(db_session_factory, i) for i in range(N_ESCRITURAS_CONCURRENTES)]
    )

    async with db_session_factory() as session:
        repositorio = SQLAlchemyTrazabilidadRepository(session)
        use_case = VerificarIntegridadRegistroUseCase(repositorio)
        resultado = await use_case.execute()

    assert resultado.total_registros == N_ESCRITURAS_CONCURRENTES
    assert resultado.integra is True
    assert resultado.primer_registro_inconsistente is None


async def test_escrituras_concurrentes_producen_cadena_estrictamente_lineal(db_session_factory):
    """Verificación más fuerte que la anterior: cada previous_hash debe ser
    exactamente el hash_actual del registro insertado inmediatamente antes
    (mismo orden de created_at) — descarta bifurcaciones que por casualidad
    aún pasaran la verificación agregada de integridad."""
    await asyncio.gather(
        *[_registrar_un_evento(db_session_factory, i) for i in range(N_ESCRITURAS_CONCURRENTES)]
    )

    async with db_session_factory() as session:
        repositorio = SQLAlchemyTrazabilidadRepository(session)
        registros = await repositorio.listar_todos_ordenados()

    assert len(registros) == N_ESCRITURAS_CONCURRENTES
    for anterior, actual in pairwise(registros):
        assert actual.previous_hash == anterior.hash_actual, (
            "Cadena bifurcada: el previous_hash de un registro no coincide con el "
            "hash_actual del registro inmediatamente anterior."
        )
