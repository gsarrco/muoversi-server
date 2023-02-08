import logging
import os
import re
import sys
from datetime import datetime, time
from sqlite3 import Connection

import yaml

from babel.dates import format_date
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters, CallbackQueryHandler,
)

from .db import DBFile
from .helpers import StopData, split_list, LIMIT, get_time

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

current_dir = os.path.abspath(os.path.dirname(__file__))
parent_dir = os.path.abspath(current_dir + "/../")
thismodule = sys.modules[__name__]
thismodule.aut_db_con = None
thismodule.nav_db_con = None

SEARCH_STOP, SHOW_STOP, FILTER_TIMES = range(3)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Benvenuto su MuoVErsi, uno strumento avanzato per chi prende i trasporti pubblici a Venezia.\n\n"
        "Inizia la tua ricerca con /fermata_aut per il servizio automobilistico, o /fermata_nav per quello di navigazione."
    )


async def fermata_aut(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    transport_type = 'automobilistico'
    context.user_data['transport_type'] = transport_type
    reply_keyboard = [[KeyboardButton("Invia posizione", request_location=True)]]

    await update.message.reply_text(
        f"Inizia digitando il nome della fermata del servizio {transport_type} oppure invia la posizione attuale per vedere le fermate più vicine.\n\n"
        "Invia /annulla per interrompere questa conversazione.",
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, one_time_keyboard=True, input_field_placeholder="Posizione attuale"
        )
    )

    return SEARCH_STOP


async def fermata_nav(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    transport_type = 'navigazione'
    context.user_data['transport_type'] = transport_type
    reply_keyboard = [[KeyboardButton("Invia posizione", request_location=True)]]

    await update.message.reply_text(
        f"Inizia digitando il nome della fermata del servizio {transport_type} oppure invia la posizione attuale per vedere le fermate più vicine.\n\n"
        "Invia /annulla per interrompere questa conversazione.",
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, one_time_keyboard=True, input_field_placeholder="Posizione attuale"
        )
    )

    return SEARCH_STOP


async def search_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.message.from_user
    message = update.message

    if context.user_data['transport_type'] == 'automobilistico':
        cur = thismodule.aut_db_con.cursor()
    else:
        cur = thismodule.nav_db_con.cursor()

    if message.location:
        lat = message.location.latitude
        long = message.location.longitude

        result = cur.execute(
            'SELECT stop_id, stop_name FROM stops ORDER BY ((stop_lat-?)*(stop_lat-?)) + ((stop_lon-?)*(stop_lon-?)) '
            'ASC LIMIT 5',
            (lat, lat, long, long))
    else:
        result = cur.execute('SELECT stop_id, stop_name FROM stops where stop_name LIKE ? LIMIT 5',
                             ('%' + message.text + '%',))

    stop_results = result.fetchall()
    if not stop_results:
        await update.message.reply_text('Non abbiamo trovato la fermata che hai inserito. Riprova.')
        return SEARCH_STOP

    stops = []

    for stop in stop_results:
        stop_id, stop_name = stop
        stoptime_results = cur.execute(
            'SELECT stop_headsign, count(stop_headsign) as headsign_count FROM stop_times WHERE stop_id = ? '
            'GROUP BY stop_headsign ORDER BY headsign_count DESC LIMIT 2;',
            (stop_id,)).fetchall()
        if stoptime_results:
            count = sum([stoptime[1] for stoptime in stoptime_results])
            headsigns = '/'.join([stoptime[0] for stoptime in stoptime_results])
        else:
            count, headsigns = 0, '*NO ORARI*'

        stops.append((stop_id, stop_name, headsigns, count))

    if not message.location:
        stops.sort(key=lambda x: -x[3])
    buttons = [[f'{stop_name} ({stop_id}) - {headsigns}'] for stop_id, stop_name, headsigns, count in stops]

    await update.message.reply_text(
        "Scegli la fermata",
        reply_markup=ReplyKeyboardMarkup(
            buttons, one_time_keyboard=True, input_field_placeholder="Scegli la fermata"
        )
    )

    return SHOW_STOP


async def show_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.user_data['transport_type'] == 'automobilistico':
        con = thismodule.aut_db_con
    else:
        con = thismodule.nav_db_con

    buttons = [str(i) for i in range(1, LIMIT + 1)]
    reply_markup = ReplyKeyboardMarkup(split_list(buttons), resize_keyboard=True)
    await update.message.reply_text('Ecco gli orari', disable_notification=True, reply_markup=reply_markup)

    stop_id = re.search(r'.*\((\d+)\).*', update.message.text).group(1)

    now = datetime.now()

    stopdata = StopData(stop_id, now.date(), '', '', '')
    results = stopdata.get_times(con)

    if not results:
        await update.message.reply_text(
            "Non riusciamo a recuperare gli orari per questa giornata.", reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    text, reply_markup = stopdata.format_times_text(results, context)
    await update.message.reply_text(text, reply_markup=reply_markup)

    return FILTER_TIMES


async def filter_times(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data['transport_type'] == 'automobilistico':
        con = thismodule.aut_db_con
    else:
        con = thismodule.nav_db_con

    query = update.callback_query

    logger.info("Query data %s", query.data)

    stopdata = StopData(query_data=query.data)

    results = stopdata.get_times(con)
    text, reply_markup = stopdata.format_times_text(results, context)

    await query.answer(stopdata.title())
    await query.edit_message_text(text=text, reply_markup=reply_markup)
    return FILTER_TIMES


async def ride_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    times_number = int(update.message.text.replace('/', '')) - 1
    trip_id, stop_id, day, stop_sequence, line = context.user_data[times_number]

    if context.user_data['transport_type'] == 'automobilistico':
        cur = thismodule.aut_db_con.cursor()
    else:
        cur = thismodule.nav_db_con.cursor()

    query = """SELECT departure_time, stop_name
                        FROM stop_times
                                 INNER JOIN stops ON stop_times.stop_id = stops.stop_id
                        WHERE stop_times.trip_id = ?
                        AND stop_sequence >= ?
                        ORDER BY stop_sequence"""

    results = cur.execute(query, (trip_id, stop_sequence)).fetchall()

    text = format_date(day, format='full', locale='it') + ' - linea ' + line + '\n'

    for result in results:
        time_raw, stop_name = result
        time_format = get_time(time_raw).isoformat(timespec="minutes")
        text += f'\n{time_format} {stop_name}'

    await update.message.reply_text(text)
    return FILTER_TIMES


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.message.from_user
    logger.info("User %s canceled the conversation.", user.first_name)
    await update.message.reply_text(
        "Conversazione interrotta. Ti ritrovi nella schermata iniziale di MuoVErsi.\n\n"
        "Inizia la tua ricerca con /fermata_aut per il servizio automobilistico, o /fermata_nav per quello di navigazione.",
        reply_markup=ReplyKeyboardRemove()
    )

    return ConversationHandler.END


def main() -> None:
    config_path = os.path.join(parent_dir, 'config.yaml')
    with open(config_path, 'r') as config_file:
        try:
            config = yaml.safe_load(config_file)
            logger.info(config)
        except yaml.YAMLError as err:
            logger.error(err)

    thismodule.aut_db_con = DBFile('automobilistico').connect_to_database()
    thismodule.nav_db_con = DBFile('navigazione').connect_to_database()

    application = Application.builder().token(config['TOKEN']).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("fermata_aut", fermata_aut), CommandHandler("fermata_nav", fermata_nav)],
        states={
            SEARCH_STOP: [MessageHandler((filters.TEXT | filters.LOCATION) & (~ filters.COMMAND), search_stop)],
            SHOW_STOP: [MessageHandler(filters.Regex(r'.*\((\d+)\).*'), show_stop)],
            FILTER_TIMES: [CallbackQueryHandler(filter_times), MessageHandler(filters.Regex(r'\/?\d+'), ride_view)]
        },
        fallbacks=[CommandHandler("annulla", cancel)]
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler)

    if config.get('DEV', False):
        application.run_polling()
    else:
        application.run_webhook(listen='0.0.0.0', port=443, secret_token=config['SECRET_TOKEN'],
                                webhook_url=config['WEBHOOK_URL'], key=os.path.join(parent_dir, 'private.key'),
                                cert=os.path.join(parent_dir, 'cert.pem'))
