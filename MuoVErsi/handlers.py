import logging
import os
import re
import sys
from datetime import datetime

import yaml
from babel.dates import format_date
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update, KeyboardButton, InlineKeyboardMarkup, \
    InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters, CallbackQueryHandler,
)

from .db import DBFile
from .helpers import StopData, get_time, get_active_service_ids, search_lines, get_stops_from_trip_id

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

current_dir = os.path.abspath(os.path.dirname(__file__))
parent_dir = os.path.abspath(current_dir + "/../")
thismodule = sys.modules[__name__]
thismodule.aut_db_con = None
thismodule.nav_db_con = None

SPECIFY_STOP, SEARCH_STOP = range(2)
SPECIFY_LINE, SEARCH_LINE, SHOW_LINE = range(3)
FILTER_TIMES, = range(1)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Benvenuto su MuoVErsi, uno strumento avanzato per chi prende i trasporti pubblici a Venezia.\n\n"
        "Inizia la tua ricerca con /fermata_aut per il servizio automobilistico, o /fermata_nav per quello di navigazione."
    )


async def choose_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    reply_keyboard = [['Automobilistico', 'Navigazione']]
    await update.message.reply_text(
        "Quale servizio ti interessa?",
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, one_time_keyboard=True, resize_keyboard=True, input_field_placeholder="Servizio"
        )
    )

    return 0


async def specify_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message_lower = update.message.text.lower()
    if message_lower == 'automobilistico':
        context.user_data['transport_type'] = 'automobilistico'
    elif message_lower == 'navigazione':
        context.user_data['transport_type'] = 'navigazione'
    else:
        await update.message.reply_text("Servizio non valido. Riprova.")
        return ConversationHandler.END

    context.user_data['transport_type'] = message_lower
    reply_keyboard = [[KeyboardButton("Invia posizione", request_location=True)]]

    await update.message.reply_text(
        f"Inizia digitando il nome della fermata del servizio {message_lower} oppure invia la posizione attuale per "
        f"vedere le fermate più vicine.\n\n",
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, one_time_keyboard=True, resize_keyboard=True, input_field_placeholder="Posizione attuale"
        )
    )

    return SEARCH_STOP


async def search_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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

    return ConversationHandler.END


async def show_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.user_data['transport_type'] == 'automobilistico':
        con = thismodule.aut_db_con
    else:
        con = thismodule.nav_db_con

    stop_id = re.search(r'\d+', update.message.text).group(0)

    now = datetime.now()

    stopdata = StopData(stop_id, now.date(), '', '', '')
    stopdata.save_query_data(context)
    await update.message.reply_text('Ecco gli orari', disable_notification=True,
                                    reply_markup=stopdata.get_days_buttons(context))

    results = stopdata.get_times(con)

    text, reply_markup, times_history = stopdata.format_times_text(results, context.user_data.get('times_history', []))
    context.user_data['times_history'] = times_history
    await update.message.reply_text(text, reply_markup=reply_markup)

    return FILTER_TIMES


async def filter_times(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data['transport_type'] == 'automobilistico':
        con = thismodule.aut_db_con
    else:
        con = thismodule.nav_db_con

    if update.callback_query:
        query = update.callback_query

        if query.data[0] == 'R':
            trip_id, stop_id, day_raw, stop_sequence, line = query.data[1:].split('/')
            day = datetime.strptime(day_raw, '%Y%m%d').date()

            if context.user_data['transport_type'] == 'automobilistico':
                cur = thismodule.aut_db_con.cursor()
            else:
                cur = thismodule.nav_db_con.cursor()

            sql_query = """SELECT departure_time, stop_name
                                    FROM stop_times
                                             INNER JOIN stops ON stop_times.stop_id = stops.stop_id
                                    WHERE stop_times.trip_id = ?
                                    AND stop_sequence >= ?
                                    ORDER BY stop_sequence"""

            results = cur.execute(sql_query, (trip_id, stop_sequence)).fetchall()

            text = format_date(day, format='full', locale='it') + ' - linea ' + line + '\n'

            for result in results:
                time_raw, stop_name = result
                time_format = get_time(time_raw).isoformat(timespec="minutes")
                text += f'\n{time_format} {stop_name}'

            await query.answer('')
            reply_markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton('Indietro', callback_data=context.user_data['query_data'])]])
            await query.edit_message_text(text=text, reply_markup=reply_markup)
            return FILTER_TIMES

        logger.info("Query data %s", query.data)
        stopdata = StopData(query_data=query.data)
        stopdata.save_query_data(context)
    else:
        stopdata = StopData(query_data=context.user_data[update.message.text])
        stopdata.save_query_data(context)
    results = stopdata.get_times(con)
    text, reply_markup, times_history = stopdata.format_times_text(results, context.user_data.get('times_history', []))
    context.user_data['times_history'] = times_history

    if update.callback_query:
        await query.answer('')
        await query.edit_message_text(text=text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text=text, reply_markup=reply_markup)
    return FILTER_TIMES


async def specify_line(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message_lower = update.message.text.lower()
    if message_lower == 'automobilistico':
        context.user_data['transport_type'] = 'automobilistico'
    elif message_lower == 'navigazione':
        context.user_data['transport_type'] = 'navigazione'
    else:
        await update.message.reply_text("Servizio non valido. Riprova.")
        return ConversationHandler.END

    context.user_data['transport_type'] = message_lower
    reply_keyboard = [[KeyboardButton("Invia posizione", request_location=True)]]

    await update.message.reply_text(
        f"Digita il numero della linea del servizio {message_lower} interessata.", reply_markup=ReplyKeyboardRemove()
    )

    return SEARCH_LINE


async def search_line(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.user_data['transport_type'] == 'automobilistico':
        con = thismodule.aut_db_con
    else:
        con = thismodule.nav_db_con

    today = datetime.now().date()
    service_ids = get_active_service_ids(today, con)

    lines = search_lines(update.message.text, service_ids, con)

    inline_markup = InlineKeyboardMarkup([[InlineKeyboardButton(line[2], callback_data=line[0])] for line in lines])

    await update.message.reply_text(
        "Quale linea cerchi?", reply_markup=inline_markup
    )

    return SHOW_LINE


async def show_line(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.user_data['transport_type'] == 'automobilistico':
        con = thismodule.aut_db_con
    else:
        con = thismodule.nav_db_con

    query = update.callback_query

    trip_id = query.data

    stops = get_stops_from_trip_id(trip_id, con)

    text = 'Fermate:\n'

    for stop in stops:
        text += f'\n/{stop[0]} {stop[1]}'

    await query.answer('')
    await query.edit_message_text(text=text)

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.message.from_user
    context.user_data.clear()
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

    stop_handler = ConversationHandler(
        entry_points=[CommandHandler("fermata", choose_service)],
        states={
            SPECIFY_STOP: [MessageHandler(filters.TEXT, specify_stop)],
            SEARCH_STOP: [MessageHandler((filters.TEXT | filters.LOCATION), search_stop)]
        },
        fallbacks=[CommandHandler("annulla", cancel)]
    )

    line_handler = ConversationHandler(
        entry_points=[CommandHandler("linea", choose_service)],
        states={
            SPECIFY_LINE: [MessageHandler(filters.TEXT, specify_line)],
            SEARCH_LINE: [MessageHandler(filters.TEXT, search_line)],
            SHOW_LINE: [CallbackQueryHandler(show_line)]
        },
        fallbacks=[CommandHandler("annulla", cancel)]
    )

    timetable_from_stop_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r'(?:\/|\()\d+'), show_stop)],
        states={
            FILTER_TIMES: [
                CallbackQueryHandler(filter_times),
                MessageHandler(filters.Regex(r'^\-|\+1g$'), filter_times)
            ]
        },
        fallbacks=[CommandHandler("annulla", cancel)]
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(stop_handler)
    application.add_handler(line_handler)
    application.add_handler(timetable_from_stop_handler)

    if config.get('DEV', False):
        application.run_polling()
    else:
        application.run_webhook(listen='0.0.0.0', port=443, secret_token=config['SECRET_TOKEN'],
                                webhook_url=config['WEBHOOK_URL'], key=os.path.join(parent_dir, 'private.key'),
                                cert=os.path.join(parent_dir, 'cert.pem'))
