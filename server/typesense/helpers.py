from sqlalchemy import select
from typesense.collection import Collection

from server.base.models import Station, Stop


def ts_search_stations(typesense, sources: list[str], name=None, lat=None, lon=None, page=1, limit=4,
                       hide_ids: list[str] = None) -> tuple[list[Station], int]:
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

    stations = []
    for result in results['hits']:
        document = result['document']
        lat, lon = document['location']
        station = Station(id=document['id'], name=document['name'], lat=lat, lon=lon,
                          ids=document['ids'], source=document['source'], times_count=document['times_count'])
        stations.append(station)

    found = limit_hits if limit_hits else results['found']
    return stations, found


def sync_stations_typesense(typesense, session):
    stations_collection: Collection = typesense.collections['stations']

    # delete all records in typesense
    stations_collection.documents.delete({'filter_by': 'times_count:>=0'})

    # get all stations_with_stop_ids
    stmt = select(Station, Stop.id).select_from(Stop).join(Stop.station).filter(Stop.active)
    stops_stations: list[tuple[Station, str]] = session.execute(stmt).all()

    results: dict[str, tuple[Station, str]] = {}
    for stop_station in stops_stations:
        station, stop_id = stop_station
        if station.id in results:
            # += ',' + stop_id
            results[station.id] = (station, results[station.id][1] + ',' + stop_id)
        else:
            results[station.id] = (station, stop_id)

    stations_with_stop_ids: list[tuple[Station, str]] = list(results.values())

    stations_to_sync = [{
        'id': station.id,
        'name': station.name,
        'location': [station.lat, station.lon],
        'ids': stop_ids,
        'source': station.source,
        'times_count': station.times_count
    } for station, stop_ids in stations_with_stop_ids]

    if not stations_to_sync:
        return

    stations_collection.documents.import_(stations_to_sync)
