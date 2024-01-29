"""Convert sched_dep_dt and sched_arr_dt to timestamp with timezone

Revision ID: 1b91fb56e447
Revises: 9db4547bf8d2
Create Date: 2024-01-29 19:40:14.705073

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '1b91fb56e447'
down_revision = '9db4547bf8d2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # alter column sched_arr_dt from timestamp without time zone to timestamp with time zone
    op.alter_column('stop_times', 'sched_arr_dt', type_=sa.TIMESTAMP(timezone=True))
    # alter column sched_dep_dt from timestamp without time zone to timestamp with time zone
    op.alter_column('stop_times', 'sched_dep_dt', type_=sa.TIMESTAMP(timezone=True))


def downgrade() -> None:
    # alter column sched_arr_dt from timestamp with time zone to timestamp without time zone
    op.alter_column('stop_times', 'sched_arr_dt', type_=sa.TIMESTAMP(timezone=False))
    # alter column sched_dep_dt from timestamp with time zone to timestamp without time zone
    op.alter_column('stop_times', 'sched_dep_dt', type_=sa.TIMESTAMP(timezone=False))
