from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route
from telegram import Update

from server.handlers import config


def get_routes(application):
    async def telegram(request: Request) -> Response:
        if request.headers['X-Telegram-Bot-Api-Secret-Token'] != config['SECRET_TOKEN']:
            return Response(status_code=403)
        await application.update_queue.put(
            Update.de_json(data=await request.json(), bot=application.bot)
        )
        return Response()

    routes = [
        Route("/tg_bot_webhook", telegram, methods=["POST"])
    ]

    return routes
