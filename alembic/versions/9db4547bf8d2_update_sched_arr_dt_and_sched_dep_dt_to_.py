"""Update sched_arr_dt and sched_dep_dt to UTC timezone

Revision ID: 9db4547bf8d2
Revises: c3c1b8b3d9e0
Create Date: 2024-01-29 19:13:47.611283

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '9db4547bf8d2'
down_revision = 'c3c1b8b3d9e0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE stop_times SET sched_arr_dt = sched_arr_dt AT TIME ZONE 'Europe/Rome' AT TIME ZONE 'UTC' "
               "WHERE source = 'venezia-aut' OR source = 'venezia-nav'")
    op.execute("UPDATE stop_times SET sched_dep_dt = sched_dep_dt AT TIME ZONE 'Europe/Rome' AT TIME ZONE 'UTC' "
               "WHERE source = 'venezia-aut' OR source = 'venezia-nav'")


def downgrade() -> None:
    op.execute("UPDATE stop_times SET sched_arr_dt = sched_arr_dt AT TIME ZONE 'UTC' AT TIME ZONE 'Europe/Rome' "
               "WHERE source = 'venezia-aut' OR source = 'venezia-nav'")
    op.execute("UPDATE stop_times SET sched_dep_dt = sched_dep_dt AT TIME ZONE 'UTC' AT TIME ZONE 'Europe/Rome' "
               "WHERE source = 'venezia-aut' OR source = 'venezia-nav'")
