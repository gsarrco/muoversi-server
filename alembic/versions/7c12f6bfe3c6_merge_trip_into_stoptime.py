"""Merge Trip into StopTime

Revision ID: 7c12f6bfe3c6
Revises: 1f2c7b1eec8b
Create Date: 2023-11-05 09:16:46.640362

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '7c12f6bfe3c6'
down_revision = '3e63dbd74ceb'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint('stop_times_trip_id_fkey', 'stop_times', type_='foreignkey')

    # Create new fields as nullable true temporarily
    op.add_column('stop_times', sa.Column('orig_id', sa.String(), nullable=True))
    op.add_column('stop_times', sa.Column('dest_text', sa.String(), nullable=True))
    op.add_column('stop_times', sa.Column('number', sa.Integer(), nullable=True))
    op.add_column('stop_times', sa.Column('orig_dep_date', sa.Date(), nullable=True))
    op.add_column('stop_times', sa.Column('route_name', sa.String(), nullable=True))
    op.add_column('stop_times', sa.Column('source', sa.String(), server_default='treni', nullable=True))

    # populate new fields with data from trips through stop_times.trip_id
    op.execute('''
        UPDATE stop_times
        SET
            orig_id = trips.orig_id,
            dest_text = trips.dest_text,
            number = trips.number,
            orig_dep_date = trips.orig_dep_date,
            route_name = trips.route_name,
            source = trips.source
        FROM trips
        WHERE stop_times.trip_id = trips.id
    ''')

    # convert new fields to not nullable
    op.alter_column('stop_times', 'orig_id', nullable=False)
    op.alter_column('stop_times', 'dest_text', nullable=False)
    op.alter_column('stop_times', 'number', nullable=False)
    op.alter_column('stop_times', 'orig_dep_date', nullable=False)
    op.alter_column('stop_times', 'route_name', nullable=False)
    op.alter_column('stop_times', 'source', nullable=False)

    # drop trip_id column
    op.drop_column('stop_times', 'trip_id')

    # drop trips table
    op.drop_table('trips')


def downgrade() -> None:
    op.create_table('trips',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('orig_id', sa.String(), autoincrement=False, nullable=False),
                    sa.Column('dest_text', sa.String(), autoincrement=False, nullable=False),
                    sa.Column('number', sa.Integer(), autoincrement=False, nullable=False),
                    sa.Column('orig_dep_date', sa.Date(), autoincrement=False, nullable=False),
                    sa.Column('route_name', sa.String(), autoincrement=False, nullable=False),
                    sa.Column('source', sa.String(), server_default='treni', autoincrement=False, nullable=False),
                    sa.PrimaryKeyConstraint('id'),
                    sa.UniqueConstraint('source', 'number', 'orig_dep_date',
                                        name='trips_source_number_orig_dep_date_key')
                    )

    op.add_column('stop_times', sa.Column('trip_id', sa.INTEGER(), autoincrement=False, nullable=False))
    op.create_foreign_key('stop_times_trip_id_fkey', 'stop_times', 'trips', ['trip_id'], ['id'], ondelete='CASCADE')

    op.drop_column('stop_times', 'source')
    op.drop_column('stop_times', 'route_name')
    op.drop_column('stop_times', 'orig_dep_date')
    op.drop_column('stop_times', 'number')
    op.drop_column('stop_times', 'dest_text')
    op.drop_column('stop_times', 'orig_id')
