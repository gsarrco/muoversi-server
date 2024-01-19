from datetime import datetime

from sqlalchemy import text
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
from starlette.routing import Route

from server.base.models import StopTime
from server.base.source import Source
from server.sources import sources


async def home(request: Request) -> Response:
    text_response = '<html>'

    try:
        sources['venezia-treni'].session.execute(text('SELECT 1'))
    except Exception:
        return Response(status_code=500)
    else:
        text_response += '<p>Postgres connection OK</p>'

    text_response += '<ul>'
    for source in sources.values():
        if hasattr(source, 'gtfs_version'):
            text_response += f'<li>{source.name}: GTFS v.{source.gtfs_version}</li>'
        else:
            text_response += f'<li>{source.name}</li>'
    text_response += '</ul></html>'
    return Response(text_response)


async def search_stations(request: Request) -> Response:
    query = request.query_params.get('q', '')
    limit = int(request.query_params.get('limit', 4))
    hide_ids = request.query_params.get('hide_ids')
    if hide_ids:
        hide_ids = hide_ids.split(',')
    only_source = request.query_params.get('only_source')
    if only_source:
        source = sources[only_source]
        all_sources = False
    else:
        source = sources['venezia-aut']
        all_sources = True
    limit = max(1, min(limit, 10))
    stations, count = source.search_stops(name=query, all_sources=all_sources, limit=limit, hide_ids=hide_ids)
    return JSONResponse([station.as_dict() for station in stations])


async def get_stop_times(request: Request) -> Response:
    dep_stops_ids = request.query_params.get('dep_stops_ids')
    if not dep_stops_ids:
        return Response(status_code=400, content='Missing dep_stops_ids')
    arr_stops_ids = request.query_params.get('arr_stops_ids')
    direction = int(request.query_params.get('direction', 1))
    source_name = request.query_params.get('source')
    if not source_name:
        return Response(status_code=400, content='Missing source')

    start_dt_str = request.query_params.get('start_dt')
    if not start_dt_str:
        return Response(status_code=400, content='Missing start_dt')
    start_dt = datetime.fromisoformat(start_dt_str)

    end_dt_str = request.query_params.get('end_dt')
    end_dt = None
    if end_dt_str:
        end_dt = datetime.fromisoformat(end_dt_str)

    str_offset = request.query_params.get('offset_by_ids', '')

    if str_offset == '':
        offset: int = 0
    else:
        offset: tuple[int] = tuple(map(int, str_offset.split(',')))

    limit = int(request.query_params.get('limit', 10))

    if limit > 15:
        limit = 15

    source: Source = sources[source_name]

    if arr_stops_ids:
        stop_times: list[tuple[StopTime, StopTime]] = source.get_stop_times_between_stops(dep_stops_ids, arr_stops_ids,
                                                                                          '', start_dt,
                                                                                          offset, limit=limit,
                                                                                          direction=direction,
                                                                                          end_dt=end_dt)
        return JSONResponse([[stop_time[0].as_dict(), stop_time[1].as_dict()] for stop_time in stop_times])
    else:
        stop_times: list[StopTime] = source.get_stop_times(dep_stops_ids, '', start_dt, offset, limit=limit,
                                                           direction=direction, end_dt=end_dt)
        return JSONResponse([[stop_time.as_dict()] for stop_time in stop_times])
    


routes = [
    Route("/", home),
    Route("/search/stations", search_stations),
    Route("/stop_times", get_stop_times)
]
