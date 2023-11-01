"""create typesense table for stations

Revision ID: 2e8b9b6298f0
Revises: af59516d0296
Create Date: 2023-07-26 07:12:04.490257

"""
from typesense.exceptions import ObjectNotFound

from server.typesense import connect_to_typesense

# revision identifiers, used by Alembic.
revision = '2e8b9b6298f0'
down_revision = 'af59516d0296'
branch_labels = None
depends_on = None
client = connect_to_typesense()


def upgrade() -> None:
    try:
        client.collections['stations'].delete()
    except ObjectNotFound:
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
        'synonyms': ['s.', 'santo', 'santa', 'san']
    })
    client.collections['stations'].synonyms.upsert('fs-stazione', {
        'synonyms': ['fs', 'stazione']
    })
    client.collections['stations'].synonyms.upsert('f.te-fondamenta', {
        'synonyms': ['f.te', 'fondamenta', 'fondamente']
    })
    client.collections['stations'].synonyms.upsert('cap-capolinea', {
        'synonyms': ['cap.', 'capolinea']
    })


def downgrade() -> None:
    try:
        client.collections['stations'].synonyms['p-le-piazzale'].delete()
        client.collections['stations'].synonyms['s.-santo'].delete()
        client.collections['stations'].synonyms['fs-stazione'].delete()
        client.collections['stations'].synonyms['f.te-fondamenta'].delete()
        client.collections['stations'].synonyms['cap-capolinea'].delete()
        client.collections['stations'].delete()
    except ObjectNotFound:
        pass
