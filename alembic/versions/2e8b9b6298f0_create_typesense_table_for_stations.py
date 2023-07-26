"""create typesense table for stations

Revision ID: 2e8b9b6298f0
Revises: af59516d0296
Create Date: 2023-07-26 07:12:04.490257

"""

from MuoVErsi.typesense import connect_to_typesense

# revision identifiers, used by Alembic.
revision = '2e8b9b6298f0'
down_revision = 'af59516d0296'
branch_labels = None
depends_on = None
client = connect_to_typesense()


def upgrade() -> None:
    try:
        client.collections['stations'].delete()
    except Exception as e:
        pass
    client.collections.create({
        'name': 'stations',
        'fields': [
            {'name': 'id', 'type': 'string'},
            {'name': 'name', 'type': 'string'},
            {'name': 'location', 'type': 'geopoint'},
            {'name': 'ids', 'type': 'string'},
            {'name': 'source', 'type': 'string', 'facet': True},
            {'name': 'times_count', 'type': 'float'}
        ],
        'default_sorting_field': 'times_count'
    })

    client.collections['stations'].synonyms.upsert('p-le-piazzale', {
        'synonyms': ['p.le', 'piazzale']
    })
    client.collections['stations'].synonyms.upsert('s.-santo', {
        'synonyms': ['s.', 'santo', 'santa']
    })
    client.collections['stations'].synonyms.upsert('fs-stazione', {
        'synonyms': ['fs', 'stazione']
    })


def downgrade() -> None:
    client.collections['stations'].synonyms.delete('p-le-piazzale')
    client.collections['stations'].synonyms.delete('s.-santo')
    client.collections['stations'].synonyms.delete('fs-stazione')
    client.collections['stations'].delete()
