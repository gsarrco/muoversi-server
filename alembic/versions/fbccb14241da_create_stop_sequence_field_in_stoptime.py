"""Create stop_sequence field in StopTime

Revision ID: fbccb14241da
Revises: 1b91fb56e447
Create Date: 2024-02-04 11:35:31.500466

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'fbccb14241da'
down_revision = '1b91fb56e447'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index('stop_times_unique_idx', table_name='stop_times')
    op.add_column('stop_times', sa.Column('stop_sequence', sa.Integer(), nullable=True))
    op.create_unique_constraint('stop_times_unique_idx', 'stop_times',
                                ['stop_id', 'number', 'source', 'orig_dep_date', 'stop_sequence'])


def downgrade() -> None:
    op.drop_constraint('stop_times_unique_idx', 'stop_times', type_='unique')
    op.drop_column('stop_times', 'stop_sequence')
    op.create_index('stop_times_unique_idx', 'stop_times',
                    ['stop_id', 'number', 'source', 'orig_dep_date'])
