"""Rename fields to English

Revision ID: 9a2372c3d8a1
Revises: 8975604fee40
Create Date: 2023-09-14 14:55:24.798135

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9a2372c3d8a1'
down_revision = '8975604fee40'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column('trips', 'codOrigine', new_column_name='orig_id')
    op.alter_column('trips', 'numeroTreno', new_column_name='number')
    op.alter_column('trips', 'destinazione', new_column_name='dest_text')
    op.alter_column('trips', 'dataPartenzaTreno', new_column_name='orig_dep_date')
    op.alter_column('trips', 'categoria', new_column_name='route_name')

    op.alter_column('stop_times', 'idFermata', new_column_name='stop_id')
    op.alter_column('stop_times', 'arrivo_teorico', new_column_name='sched_arr_dt')
    op.alter_column('stop_times', 'partenza_teorica', new_column_name='sched_dep_dt')
    op.alter_column('stop_times', 'binario', new_column_name='platform')

def downgrade() -> None:
    op.alter_column('trips', 'orig_id', new_column_name='codOrigine')
    op.alter_column('trips', 'number', new_column_name='numeroTreno')
    op.alter_column('trips', 'dest_text', new_column_name='destinazione')
    op.alter_column('trips', 'orig_dep_date', new_column_name='dataPartenzaTreno')
    op.alter_column('trips', 'route_name', new_column_name='categoria')

    op.alter_column('stop_times', 'stop_id', new_column_name='idFermata')
    op.alter_column('stop_times', 'sched_arr_dt', new_column_name='arrivo_teorico')
    op.alter_column('stop_times', 'sched_dep_dt', new_column_name='partenza_teorica')
    op.alter_column('stop_times', 'platform', new_column_name='binario')
