import os

import yaml
from typesense import Client


def connect_to_typesense():
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(parent_dir, 'config.yaml')
    with open(config_path, 'r') as config_file:
        config = yaml.safe_load(config_file)
    return Client({
        'api_key': config['TYPESENSE_API_KEY'],
        'nodes': [{
            'host': config.get('TYPESENSE_HOST', 'localhost'),
            'port': '8108',
            'protocol': 'http'
        }],
        'connection_timeout_seconds': 2
    })


def ts_search_stations(typesense, sources: list[str], name=None, lat=None, lon=None, page=1, limit=4,
                       hide_ids: list[str] = None):
    search_config = {'per_page': limit, 'query_by': 'name', 'page': page}

    limit_hits = None
    if lat and lon:
        limit_hits = limit * 2
        search_config.update({
            'q': '*',
            'sort_by': f'location({lat},{lon}):asc',
            'limit_hits': limit_hits
        })
    else:
        search_config.update({
            'q': name,
            'sort_by': 'times_count:desc'
        })

    if sources:
        search_config['filter_by'] = f'source:[{",".join(sources)}]'
    if hide_ids:
        search_config['hidden_hits'] = ','.join(hide_ids)

    results = typesense.collections['stations'].documents.search(search_config)

    from server.base import Station

    stations = []
    for result in results['hits']:
        document = result['document']
        lat, lon = document['location']
        station = Station(id=document['id'], name=document['name'], lat=lat, lon=lon,
                          ids=document['ids'], source=document['source'], times_count=document['times_count'])
        stations.append(station)

    found = limit_hits if limit_hits else results['found']
    return stations, found
