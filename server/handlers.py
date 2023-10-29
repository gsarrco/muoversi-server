import logging

import uvicorn
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from config import config
from tgbot.handlers import setup as tgbot_setup
from .GTFS import GTFS
from .trenitalia import Trenitalia
from .typesense import connect_to_typesense

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

engine_url = f"postgresql://{config['PGUSER']}:{config['PGPASSWORD']}@{config['PGHOST']}:{config['PGPORT']}/" \
             f"{config['PGDATABASE']}"
engine = create_engine(engine_url)


async def main() -> None:
    DEV = config.get('DEV', False)

    session = sessionmaker(bind=engine)()
    typesense = connect_to_typesense()

    sources = {
        'aut': GTFS('automobilistico', '🚌', session, typesense, dev=DEV),
        'nav': GTFS('navigazione', '⛴️', session, typesense, dev=DEV),
        'treni': Trenitalia(session, typesense)
    }

    for source in sources.values():
        source.sync_stations_typesense(source.get_source_stations())

    application, tgbot_routes = await tgbot_setup(config, sources)

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

    routes = [Route("/", home)]
    routes += tgbot_routes
    starlette_app = Starlette(routes=routes)

    if DEV:
        webserver = uvicorn.Server(
            config=uvicorn.Config(
                app=starlette_app,
                port=8000,
                host="127.0.0.1",
            )
        )
    else:
        webserver = uvicorn.Server(
            config=uvicorn.Config(
                app=starlette_app,
                port=443,
                host="0.0.0.0",
                ssl_keyfile=config['SSL_KEYFILE'],
                ssl_certfile=config['SSL_CERTFILE']
            )
        )

    async with application:
        await application.start()
        await webserver.serve()
        await application.stop()
