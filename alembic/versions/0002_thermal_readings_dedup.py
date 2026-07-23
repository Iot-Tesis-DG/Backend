"""deduplicación de lecturas térmicas: restricción única (device_id, timestamp)

Corrige el hallazgo B-04 de la auditoría: un reenvío MQTT (PUBACK perdido,
QoS1) para el mismo dispositivo y el mismo instante exacto no debe producir
un segundo registro en `thermal_readings`.

Revision ID: 0002_thermal_readings_dedup
Revises: 0001_initial_schema
Create Date: 2026-07-22

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_thermal_readings_dedup"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONSTRAINT_NAME = "uq_thermal_readings_device_timestamp"


def upgrade() -> None:
    op.create_unique_constraint(
        CONSTRAINT_NAME, "thermal_readings", ["device_id", "timestamp"]
    )


def downgrade() -> None:
    op.drop_constraint(CONSTRAINT_NAME, "thermal_readings", type_="unique")
