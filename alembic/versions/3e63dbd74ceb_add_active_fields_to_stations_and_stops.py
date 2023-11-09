"""Add active fields to stations and stops

Revision ID: 3e63dbd74ceb
Revises: 1f2c7b1eec8b
Create Date: 2023-11-09 16:37:09.843639

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3e63dbd74ceb'
down_revision = '1f2c7b1eec8b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('stations', sa.Column('active', sa.Boolean(), server_default='true', nullable=False))
    op.add_column('stops', sa.Column('active', sa.Boolean(), server_default='true', nullable=False))


def downgrade() -> None:
    op.drop_column('stops', 'active')
    op.drop_column('stations', 'active')
