"""Rename trains in db

Revision ID: 9cf53fbd990e
Revises: 6c9ef3a680e3
Create Date: 2023-09-14 14:28:04.028850

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9cf53fbd990e'
down_revision = '6c9ef3a680e3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # rename trains table to trips
    op.rename_table('trains', 'trips')

    # rename train_id column to trip_id on stop_times table
    op.alter_column('stop_times', 'train_id', new_column_name='trip_id')


def downgrade() -> None:
    # rename trips table to trains
    op.rename_table('trips', 'trains')

    # rename trip_id column to train_id on stop_times table
    op.alter_column('stop_times', 'trip_id', new_column_name='train_id')
