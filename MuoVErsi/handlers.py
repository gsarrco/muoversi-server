import logging
import os
import re
import sys
from datetime import datetime
from sqlite3 import Connection

import yaml
from babel.dates import format_date
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update, KeyboardButton, InlineKeyboardMarkup, \
    InlineKeyboardButton, Message
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters, CallbackQueryHandler,
)

from .db import DBFile
from .helpers import StopData, get_time, get_active_service_ids, search_lines, get_stops_from_trip_id, search_stops

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

current_dir = os.path.abspath(os.path.dirname(__file__))
parent_dir = os.path.abspath(current_dir + "/../")
thismodule = sys.modules[__name__]
thismodule.aut_db_con = None
thismodule.nav_db_con = None

SPECIFY_STOP, SEARCH_STOP, SPECIFY_LINE, SEARCH_LINE, SHOW_LINE, SHOW_STOP = range(6)

HOME_TEXT = "Inizia la tua ricerca con /fermata per partire da una fermata, o /linea per una linea."


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Benvenuto su MuoVErsi, uno strumento avanzato per chi prende i trasporti pubblici a Venezia.\n\n" + HOME_TEXT
    )


async def choose_service(update: Update, context: ContextTypes.DEFAULT_TYPE, command) -> int:
    context.user_data.clear()
    inline_keyboard = [[InlineKeyboardButton("Automobilistico", callback_data="automobilistico"),
                        InlineKeyboardButton("Navigazione", callback_data="navigazione")]]
    await update.message.reply_text(
        f"Stai cercando per {command}.\n\nQuale servizio di Actv ti interessa?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard)
    )

    if command == 'fermata':
        return SPECIFY_STOP

    return SPECIFY_LINE


async def choose_service_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await choose_service(update, context, 'fermata')


async def choose_service_line(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await choose_service(update, context, 'linea')


async def specify(update: Update, context: ContextTypes.DEFAULT_TYPE, command) -> int:
    query = update.callback_query
    chat_id = query.message.chat_id
    transport_type = query.data

    context.user_data['transport_type'] = transport_type

    if command == 'fermata':
        reply_keyboard = [[KeyboardButton("Invia posizione", request_location=True)]]
        reply_keyboard_markup = ReplyKeyboardMarkup(
            reply_keyboard, one_time_keyboard=True, resize_keyboard=True,
            input_field_placeholder="Posizione attuale"
        )
    else:
        reply_keyboard_markup = ReplyKeyboardRemove()

    await query.answer('')

    if command == 'fermata':
        text = "Inizia digitando il nome della fermata oppure invia la posizione tua attuale o di un altro luogo per " \
               "vedere le fermate più vicine."
    else:
        text = 'Digita il numero della linea interessata.'

    await query.get_bot().send_message(chat_id,
       f"Hai selezionato il servizio {transport_type}.\n\n{text}",
       reply_markup=reply_keyboard_markup
    )

    if command == 'fermata':
        return SEARCH_STOP

    return SEARCH_LINE


async def specify_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await specify(update, context, 'fermata')


async def search_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message

    if context.user_data['transport_type'] == 'automobilistico':
        con: Connection = thismodule.aut_db_con.con
    else:
        con: Connection = thismodule.nav_db_con.con

    if message.location:
        lat = message.location.latitude
        lon = message.location.longitude
        stops_clusters = search_stops(con, lat=lat, lon=lon)
    else:
        stops_clusters = search_stops(con, name=message.text)

    if not stops_clusters:
        await update.message.reply_text('Non abbiamo trovato la fermata che hai inserito. Riprova.')
        return SEARCH_STOP

    buttons = [[InlineKeyboardButton(cluster_name, callback_data=f'S{cluster_id}')]
               for cluster_id, cluster_name in stops_clusters]

    await update.message.reply_text(
        "Scegli la fermata",
        reply_markup=InlineKeyboardMarkup(
            buttons
        )
    )

    return SHOW_STOP


async def show_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.user_data['transport_type'] == 'automobilistico':
        con = thismodule.aut_db_con.con
    else:
        con = thismodule.nav_db_con.con

    first_message = False
    if update.callback_query:
        query = update.callback_query

        if query.data[0] == 'R':
            trip_id, day_raw, stop_sequence, line = query.data[1:].split('/')
            day = datetime.strptime(day_raw, '%Y%m%d').date()

            results = get_stops_from_trip_id(trip_id, con, stop_sequence)

            text = format_date(day, format='full', locale='it') + ' - linea ' + line + '\n'

            for result in results:
                _, stop_name, time_raw = result
                time_format = get_time(time_raw).isoformat(timespec="minutes")
                text += f'\n{time_format} {stop_name}'

            await query.answer('')
            reply_markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton('Indietro', callback_data=context.user_data['query_data'])]])
            await query.edit_message_text(text=text, reply_markup=reply_markup)
            return SHOW_STOP

        if query.data[0] == 'S':
            cluster_id = query.data[1:]
            now = datetime.now()
            stopdata = StopData(cluster_id, now.date(), '', '', '')
            first_message = True
        else:
            logger.info("Query data %s", query.data)
            stopdata = StopData(query_data=query.data)
    else:
        if update.message.text == '-1g' or update.message.text == '+1g':
            stopdata = StopData(query_data=context.user_data[update.message.text])
        else:
            stop_id = re.search(r'\d+', update.message.text).group(0)
            now = datetime.now()
            stopdata = StopData(stop_id, now.date(), '', '', '')
            first_message = True

    stopdata.save_query_data(context)

    if update.callback_query:
        chat_id = update.callback_query.message.chat_id
        bot = update.callback_query.get_bot()
    else:
        chat_id = update.message.chat_id
        bot = update.message.get_bot()

    if first_message:
        await bot.send_message(chat_id, 'Ecco gli orari', disable_notification=True,
                                        reply_markup=ReplyKeyboardMarkup([['-1g', '+1g']], resize_keyboard=True))

    results = stopdata.get_times(con)

    text, reply_markup, times_history = stopdata.format_times_text(results, context.user_data.get('times_history', []))
    context.user_data['times_history'] = times_history

    if update.callback_query:
        await query.answer('')

    if not update.callback_query or first_message:
        await bot.send_message(chat_id, text=text, reply_markup=reply_markup, parse_mode='HTML')
        return SHOW_STOP

    await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode='HTML')
    return SHOW_STOP


async def specify_line(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await specify(update, context, 'linea')


async def search_line(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.user_data['transport_type'] == 'automobilistico':
        con = thismodule.aut_db_con.con
    else:
        con = thismodule.nav_db_con.con

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
        con = thismodule.aut_db_con.con
    else:
        con = thismodule.nav_db_con.con

    query = update.callback_query

    trip_id = query.data

    stops = get_stops_from_trip_id(trip_id, con)

    text = 'Fermate:\n'

    for stop in stops:
        text += f'\n/{stop[0]} {stop[1]}'

    await query.answer('')
    await query.edit_message_text(text=text)

    return SHOW_STOP


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.message.from_user
    context.user_data.clear()
    logger.info("User %s canceled the conversation.", user.first_name)
    await update.message.reply_text(
        "Conversazione interrotta. Ti ritrovi nella schermata iniziale di MuoVErsi.\n\n"  + HOME_TEXT,
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

    DEV = config.get('DEV', False)

    thismodule.aut_db_con = DBFile('automobilistico')
    if DEV:
        thismodule.aut_db_con.con.set_trace_callback(logger.info)
    logger.info('automobilistico DBFile initialized')
    stops_clusters_uploaded = thismodule.aut_db_con.upload_stops_clusters_to_db()
    logger.info('automobilistico stops clusters uploaded: %s', stops_clusters_uploaded)

    thismodule.nav_db_con = DBFile('navigazione')
    if DEV:
        thismodule.nav_db_con.con.set_trace_callback(logger.info)
    logger.info('navigazione DBFile initialized')
    stops_clusters_uploaded = thismodule.nav_db_con.upload_stops_clusters_to_db()
    logger.info('navigazione stops clusters uploaded: %s', stops_clusters_uploaded)

    application = Application.builder().token(config['TOKEN']).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("fermata", choose_service_stop), CommandHandler("linea", choose_service_line)],
        states={
            SPECIFY_STOP: [CallbackQueryHandler(specify_stop)],
            SEARCH_STOP: [MessageHandler((filters.TEXT | filters.LOCATION) & (~filters.COMMAND), search_stop)],
            SPECIFY_LINE: [CallbackQueryHandler(specify_line)],
            SEARCH_LINE: [MessageHandler(filters.TEXT & (~filters.COMMAND), search_line)],
            SHOW_LINE: [CallbackQueryHandler(show_line)],
            SHOW_STOP: [
                MessageHandler(filters.Regex(r'(?:\/|\()\d+'), show_stop),
                CallbackQueryHandler(show_stop),
                MessageHandler(filters.Regex(r'^\-|\+1g$'), show_stop)
            ]
        },
        fallbacks=[CommandHandler("annulla", cancel), CommandHandler("fermata", choose_service_stop),
                   CommandHandler("linea", choose_service_line)]
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler)

    if DEV:
        application.run_polling()
    else:
        application.run_webhook(listen='0.0.0.0', port=443, secret_token=config['SECRET_TOKEN'],
                                webhook_url=config['WEBHOOK_URL'], key=os.path.join(parent_dir, 'private.key'),
                                cert=os.path.join(parent_dir, 'cert.pem'))
