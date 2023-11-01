import asyncio
import logging

import uvicorn
from starlette.applications import Starlette

from config import config
from server.routes import routes as server_routes

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


async def run() -> None:
    routes = server_routes

    tgbot_application = None
    if config['TG_BOT_ENABLED']:
        from tgbot.handlers import set_up_application
        tgbot_application = await set_up_application()
        from tgbot.routes import get_routes as get_tgbot_routes
        routes += get_tgbot_routes(tgbot_application)

    starlette_app = Starlette(routes=routes)

    if config.get('DEV', False):
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

    if tgbot_application:
        async with tgbot_application:
            await tgbot_application.start()
            await webserver.serve()
            await tgbot_application.stop()
    else:
        await webserver.serve()

if __name__ == "__main__":
    asyncio.run(run())
