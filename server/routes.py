from sqlalchemy import text
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
from starlette.routing import Route

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
    query = request.path_params['query']
    stations, count = sources['aut'].search_stops(name=query, all_sources=True)
    return JSONResponse([station.as_dict() for station in stations])


routes = [
    Route("/", home),
    Route("/search/stations/{query:str}", search_stations)
]
