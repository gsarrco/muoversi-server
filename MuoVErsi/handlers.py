import logging
import os
import re
import sqlite3
from datetime import datetime, time
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

from .helpers import StopData, split_list, limit, get_time

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

current_dir = os.path.abspath(os.path.dirname(__file__))
parent_dir = os.path.abspath(current_dir + "/../")
db_path = os.path.join(parent_dir, 'data.db')
con = sqlite3.connect(db_path)
con.set_trace_callback(logger.info)

SEARCH_STOP, SHOW_STOP, FILTER_TIMES = range(3)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Benvenuto su MuoVErsi, uno strumento avanzato per chi prende i trasporti pubblici a Venezia.\n\n"
        "Inizia la tua ricerca con /fermata."
    )


async def fermata(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    reply_keyboard = [[KeyboardButton("Invia posizione", request_location=True)]]

    await update.message.reply_text(
        "Inizia digitando il nome della fermata oppure invia la posizione attuale per vedere le fermate più vicine.\n\n"
        "Invia /annulla per interrompere questa conversazione.",
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, one_time_keyboard=True, input_field_placeholder="Posizione attuale"
        )
    )

    return SEARCH_STOP


async def search_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.message.from_user
    message = update.message
    cur = con.cursor()
    if message.location:
        lat = message.location.latitude
        long = message.location.longitude

        result = cur.execute(
            'SELECT stop_id, stop_name FROM stops ORDER BY ((stop_lat-?)*(stop_lat-?)) + ((stop_lon-?)*(stop_lon-?)) '
            'ASC LIMIT 5',
            (lat, lat, long, long))
    else:
        result = cur.execute('SELECT stop_id, stop_name FROM stops where stop_name LIKE ?', ('%' + message.text + '%',))

    results = result.fetchall()
    if not results:
        await update.message.reply_text('Non abbiamo trovato la fermata che hai inserito. Riprova.')
        return SEARCH_STOP

    stops = []
    for stop in results:
        stop_id, stop_name = stop
        results = cur.execute(
            'SELECT DISTINCT stop_headsign, count(*) OVER() AS full_count FROM stop_times WHERE stop_id = ?',
            (stop_id,))
        results = results.fetchall()[:2]
        count = results[0][1]
        headsigns = '/'.join([result[0] for result in results])
        stops.append((stop_id, stop_name, headsigns, count))

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
    buttons = [str(i) for i in range(1, limit + 1)]
    reply_markup = ReplyKeyboardMarkup(split_list(buttons), resize_keyboard=True)
    await update.message.reply_text('Ecco gli orari', disable_notification=True, reply_markup=reply_markup)

    stop_id = re.search(r'.*\((\d+)\).*', update.message.text).group(1)

    now = datetime.now()

    stopdata = StopData()
    stopdata.stop_id = stop_id
    stopdata.day = now.date()
    stopdata.line = ''
    stopdata.start_time = time(0, 0, 0)
    stopdata.end_time = time(23, 59, 59)
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
    query = update.callback_query

    logger.info("Query data %s", query.data)

    stopdata = StopData(query.data)

    results = stopdata.get_times(con)
    text, reply_markup = stopdata.format_times_text(results, context)

    await query.answer(stopdata.title())
    await query.edit_message_text(text=text, reply_markup=reply_markup)
    return FILTER_TIMES


async def ride_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    times_number = int(update.message.text.replace('/', '')) - 1
    trip_id, stop_id, day, stop_sequence, line = context.user_data[times_number]

    query = """SELECT departure_time, stop_name
                        FROM stop_times
                                 INNER JOIN stops ON stop_times.stop_id = stops.stop_id
                        WHERE stop_times.trip_id = ?
                        AND stop_sequence >= ?
                        ORDER BY stop_sequence"""

    results = con.execute(query, (trip_id, stop_sequence)).fetchall()

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
        "Inizia la tua ricerca con /fermata.",
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

    application = Application.builder().token(config['TOKEN']).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("fermata", fermata)],
        states={
            SEARCH_STOP: [MessageHandler((filters.TEXT | filters.LOCATION) & (~ filters.COMMAND), search_stop)],
            SHOW_STOP: [MessageHandler(filters.Regex(r'.*\((\d+)\).*'), show_stop)],
            FILTER_TIMES: [CallbackQueryHandler(filter_times), MessageHandler(filters.Regex(r'\/?\d+'), ride_view)]
        },
        fallbacks=[CommandHandler("annulla", cancel)]
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler)

    if os.environ.get('ENV') == 'dev':
        application.run_polling()
    else:
        application.run_webhook(listen='0.0.0.0', port=443, secret_token=config['SECRET_TOKEN'],
                                webhook_url=config['WEBHOOK_URL'], key=os.path.join(parent_dir, 'private.key'),
                                cert=os.path.join(parent_dir, 'cert.pem'))
