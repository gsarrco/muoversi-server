"""add ids field to Station

Revision ID: 484c6175c204
Revises: c5dfc670b459
Create Date: 2023-07-18 18:29:00.545983

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '484c6175c204'
down_revision = 'c5dfc670b459'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('stations', sa.Column('ids', sa.String(), server_default='', nullable=False))

    op.execute('UPDATE stations SET ids = id')
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('stations', 'ids')
    # ### end Alembic commands ###
