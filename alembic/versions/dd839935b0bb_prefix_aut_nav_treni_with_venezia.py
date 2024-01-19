"""Prefix aut, nav, treni with venezia

Revision ID: dd839935b0bb
Revises: d55702afa188
Create Date: 2024-01-19 15:11:41.149726

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'dd839935b0bb'
down_revision = 'd55702afa188'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # in stations rename aut to venezia-aut, nav to venezia-nav, treni to venezia-treni
    op.execute("UPDATE stations SET source='venezia-aut' WHERE source='aut'")
    op.execute("UPDATE stations SET source='venezia-nav' WHERE source='nav'")
    op.execute("UPDATE stations SET source='venezia-treni' WHERE source='treni'")

    # in stops rename aut to venezia-aut, nav to venezia-nav, treni to venezia-treni
    op.execute("UPDATE stops SET source='venezia-aut' WHERE source='aut'")
    op.execute("UPDATE stops SET source='venezia-nav' WHERE source='nav'")
    op.execute("UPDATE stops SET source='venezia-treni' WHERE source='treni'")

    # in stop_times rename aut to venezia-aut, nav to venezia-nav, treni to venezia-treni
    op.execute("UPDATE stop_times SET source='venezia-aut' WHERE source='aut'")
    op.execute("UPDATE stop_times SET source='venezia-nav' WHERE source='nav'")
    op.execute("UPDATE stop_times SET source='venezia-treni' WHERE source='treni'")


def downgrade() -> None:
    # in stations rename venezia-aut to aut, venezia-nav to nav, venezia-treni to treni
    op.execute("UPDATE stations SET source='aut' WHERE source='venezia-aut'")
    op.execute("UPDATE stations SET source='nav' WHERE source='venezia-nav'")
    op.execute("UPDATE stations SET source='treni' WHERE source='venezia-treni'")

    # in stops rename venezia-aut to aut, venezia-nav to nav, venezia-treni to treni
    op.execute("UPDATE stops SET source='aut' WHERE source='venezia-aut'")
    op.execute("UPDATE stops SET source='nav' WHERE source='venezia-nav'")
    op.execute("UPDATE stops SET source='treni' WHERE source='venezia-treni'")

    # in stop_times rename venezia-aut to aut, venezia-nav to nav, venezia-treni to treni
    op.execute("UPDATE stop_times SET source='aut' WHERE source='venezia-aut'")
    op.execute("UPDATE stop_times SET source='nav' WHERE source='venezia-nav'")
    op.execute("UPDATE stop_times SET source='treni' WHERE source='venezia-treni'")
