"""add source field to trips

Revision ID: 1f2c7b1eec8b
Revises: e07191853dcb
Create Date: 2023-10-01 16:46:36.372782

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1f2c7b1eec8b'
down_revision = 'e07191853dcb'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('trips', sa.Column('source', sa.String(), server_default='treni', nullable=False))
    op.drop_constraint('trains_codOrigine_numeroTreno_dataPartenzaTreno_key', 'trips', type_='unique')

    # update foreign key of stop_times.trip_id to cascade on delete
    op.drop_constraint('stop_times_train_id_fkey', 'stop_times', type_='foreignkey')
    op.create_foreign_key('stop_times_trip_id_fkey', 'stop_times', 'trips', ['trip_id'], ['id'], ondelete='CASCADE')

    # remove duplicates of source, number, orig_dep_date from trips table
    op.execute('DELETE FROM trips WHERE id IN (SELECT id FROM (SELECT id, ROW_NUMBER() OVER (partition BY source, number, orig_dep_date ORDER BY id) AS rnum FROM trips) t WHERE t.rnum > 1);')

    op.create_unique_constraint('trips_source_number_orig_dep_date_key', 'trips', ['source', 'number', 'orig_dep_date'])



def downgrade() -> None:
    op.drop_constraint('trips_source_number_orig_dep_date_key', 'trips', type_='unique')
    op.create_unique_constraint('trains_codOrigine_numeroTreno_dataPartenzaTreno_key', 'trips', ['orig_id', 'number', 'orig_dep_date'])
    op.drop_column('trips', 'source')
    op.drop_constraint('stop_times_trip_id_fkey', 'stop_times', type_='foreignkey')
    op.create_foreign_key('stop_times_train_id_fkey', 'stop_times', 'trips', ['trip_id'], ['id'])
