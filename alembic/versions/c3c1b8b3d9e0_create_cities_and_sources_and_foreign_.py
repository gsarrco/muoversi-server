"""Create cities and sources and foreign keys

Revision ID: c3c1b8b3d9e0
Revises: dd839935b0bb
Create Date: 2024-01-22 15:32:38.516778

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'c3c1b8b3d9e0'
down_revision = 'dd839935b0bb'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # create cities
    op.create_table('cities',
                    sa.Column('name', sa.String(), nullable=False),
                    sa.PrimaryKeyConstraint('name')
                    )
    # populate cities with venezia
    op.execute("INSERT INTO cities (name) VALUES ('venezia')")

    # create sources
    op.create_table('sources',
                    sa.Column('name', sa.String(), nullable=False),
                    sa.Column('city_name', sa.String(), nullable=False),
                    sa.Column('color', sa.String(), nullable=False),
                    sa.Column('icon_code', sa.Integer(), nullable=False),
                    sa.ForeignKeyConstraint(['city_name'], ['cities.name'], ),
                    sa.PrimaryKeyConstraint('name')
                    )

    # populate sources with venezia-aut, venezia-nav, venezia-treni
    op.execute("INSERT INTO sources (name, city_name, color, icon_code)"
               "VALUES ('venezia-aut', 'venezia', '#FF9800', 57813)")
    op.execute("INSERT INTO sources (name, city_name, color, icon_code)"
               "VALUES ('venezia-nav', 'venezia', '#2196F3', 57811)")
    op.execute("INSERT INTO sources (name, city_name, color, icon_code) "
               "VALUES ('venezia-treni', 'venezia', '#4CAF50', 58997)")

    # create foreign keys
    op.create_foreign_key('stations_source_fkey', 'stations', 'sources',
                          ['source'], ['name'])
    op.create_foreign_key('stop_times_source_fkey', 'stop_times', 'sources',
                          ['source'], ['name'])

    op.alter_column('stops', 'source',
                    existing_type=sa.VARCHAR(),
                    nullable=False)
    op.create_foreign_key('stops_source_fkey', 'stops', 'sources',
                          ['source'], ['name'])


def downgrade() -> None:
    op.drop_constraint('stops_source_fkey', 'stops', type_='foreignkey')
    op.alter_column('stops', 'source',
                    existing_type=sa.VARCHAR(),
                    nullable=True)
    op.drop_constraint('stop_times_source_fkey', 'stop_times', type_='foreignkey')
    op.drop_constraint('stations_source_fkey', 'stations', type_='foreignkey')
    op.drop_table('sources')
    op.drop_table('cities')
