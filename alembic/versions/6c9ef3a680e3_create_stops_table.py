"""Create stops table

Revision ID: 6c9ef3a680e3
Revises: 2e8b9b6298f0
Create Date: 2023-09-06 11:38:22.064834

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import sessionmaker

from server.base import Station

# revision identifiers, used by Alembic.
revision = '6c9ef3a680e3'
down_revision = '2e8b9b6298f0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    stops_table = op.create_table('stops',
                    sa.Column('id', sa.String(), nullable=False),
                    sa.Column('platform', sa.String(), nullable=True),
                    sa.Column('lat', sa.Float(), nullable=False),
                    sa.Column('lon', sa.Float(), nullable=False),
                    sa.Column('station_id', sa.String(), nullable=False),
                    sa.ForeignKeyConstraint(['station_id'], ['stations.id'], ),
                    sa.PrimaryKeyConstraint('id')
                    )
    
    # populate stops table from stations table
    session = sessionmaker(bind=op.get_bind())()
    bulk_inserts = []
    for station in session.scalars(sa.select(Station)).all():
        bulk_inserts.append({
            'id': station.id,
            'lat': station.lat,
            'lon': station.lon,
            'station_id': station.id,
        })
    op.bulk_insert(stops_table, bulk_inserts)


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('stops')
    # ### end Alembic commands ###
