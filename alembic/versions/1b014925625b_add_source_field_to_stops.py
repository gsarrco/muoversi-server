"""Add source field to stops

Revision ID: 1b014925625b
Revises: 9a2372c3d8a1
Create Date: 2023-09-14 15:59:06.795252

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1b014925625b'
down_revision = '9a2372c3d8a1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('stops', sa.Column('source', sa.String(), nullable=True))

    # populate source column from stations.source through stops.station_id
    op.execute(
        """
        UPDATE stops
        SET source = stations.source
        FROM stations
        WHERE stops.station_id = stations.id
        """
    )


def downgrade() -> None:
    op.drop_column('stops', 'source')
