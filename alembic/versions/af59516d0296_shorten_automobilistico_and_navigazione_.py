"""shorten automobilistico and navigazione texts

Revision ID: af59516d0296
Revises: 6b3b7895d0a3
Create Date: 2023-07-24 20:23:34.339586

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'af59516d0296'
down_revision = '6b3b7895d0a3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE stations SET source = 'aut' WHERE source = 'automobilistico'")
    op.execute("UPDATE stations SET source = 'nav' WHERE source = 'navigazione'")
    pass


def downgrade() -> None:
    op.execute("UPDATE stations SET source = 'automobilistico' WHERE source = 'aut'")
    op.execute("UPDATE stations SET source = 'navigazione' WHERE source = 'nav'")
    pass
