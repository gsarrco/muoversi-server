"""Create stops table

Revision ID: 6c9ef3a680e3
Revises: 2e8b9b6298f0
Create Date: 2023-09-06 11:38:22.064834

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '6c9ef3a680e3'
down_revision = '2e8b9b6298f0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('stops',
                    sa.Column('id', sa.String(), nullable=False),
                    sa.Column('platform', sa.String(), nullable=True),
                    sa.Column('lat', sa.Float(), nullable=False),
                    sa.Column('lon', sa.Float(), nullable=False),
                    sa.Column('station_id', sa.String(), nullable=False),
                    sa.ForeignKeyConstraint(['station_id'], ['stations.id'], ),
                    sa.PrimaryKeyConstraint('id')
                    )
    
    # populate stops table from stations table with id, lat, lon, station_id
    op.execute(
        """
        INSERT INTO stops (id, lat, lon, station_id)
        SELECT id, lat, lon, id
        FROM stations
        """
    )


def downgrade() -> None:
    op.drop_table('stops')
