from datetime import date, datetime

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
        sources['treni'].session.execute(text('SELECT 1'))
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
    limit = max(1, min(limit, 10))
    stations, count = sources['aut'].search_stops(name=query, all_sources=True, limit=limit)
    return JSONResponse([station.as_dict() for station in stations])


async def get_stop_times(request: Request) -> Response:
    dep_stops_ids = request.query_params.get('dep_stops_ids')
    if not dep_stops_ids:
        return Response(status_code=400, content='Missing dep_stops_ids')
    source_name = request.query_params.get('source')
    if not source_name:
        return Response(status_code=400, content='Missing source')
    day = request.query_params.get('day')
    if not day:
        return Response(status_code=400, content='Missing day')
    offset = int(request.query_params.get('offset', 0))
    limit = int(request.query_params.get('limit', 10))

    day = date.fromisoformat(day)

    # start time can only be either now, if today, or empty (start of the day) for next days
    start_time = datetime.now().time() if day == date.today() else ''

    source: Source = sources[source_name]

    stop_times: list[StopTime] = source.get_stop_times(dep_stops_ids, '', start_time, day, offset, limit=limit)
    return JSONResponse([stop_time.as_dict() for stop_time in stop_times])
    


routes = [
    Route("/", home),
    Route("/search/stations", search_stations),
    Route("/stop_times", get_stop_times)
]
