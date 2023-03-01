import gettext
import gettext
import logging
import os
import re
import sys
from datetime import datetime, timedelta

import requests
import yaml
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update, KeyboardButton, InlineKeyboardMarkup, \
    InlineKeyboardButton, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters, CallbackQueryHandler, )

from .db import DBFile
from .helpers import time_25_to_1, get_active_service_ids, search_lines, get_stops_from_trip_id
from .persistence import SQLitePersistence
from .stop_times_filter import StopTimesFilter

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

localedir = os.path.join(parent_dir, 'locales')


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = 'it' if update.effective_user.language_code == 'it' else 'en'
    trans = gettext.translation('messages', localedir, languages=[lang])
    _ = trans.gettext
    await update.message.reply_text(_('welcome') + "\n\n" + _('home') % (_('stop'), _('line')))


async def choose_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = 'it' if update.effective_user.language_code == 'it' else 'en'
    trans = gettext.translation('messages', localedir, languages=[lang])
    _ = trans.gettext

    if update.message.text[1:] == _('stop'):
        command = 'fermata'
    elif update.message.text[1:] == _('line'):
        command = 'linea'
    else:
        return ConversationHandler.END

    context.user_data.pop('query_data', None)
    context.user_data.pop('lines', None)
    context.user_data.pop('service_ids', None)
    context.user_data.pop('stop_ids', None)

    if context.user_data.get('transport_type'):
        return await specify(update, context, command)

    inline_keyboard = [[InlineKeyboardButton(_('aut'), callback_data="0aut"),
                        InlineKeyboardButton(_('nav'), callback_data="0nav")]]
    await update.message.reply_text(
        _('choose_service'),
        reply_markup=InlineKeyboardMarkup(inline_keyboard)
    )

    if command == 'fermata':
        return SPECIFY_STOP

    return SPECIFY_LINE


async def specify(update: Update, context: ContextTypes.DEFAULT_TYPE, command) -> int:
    send_second_message = True
    if update.callback_query:
        query = update.callback_query
        if query.data[0] == '1':
            send_second_message = False
        chat_id = query.message.chat_id
        short_transport_type = query.data[1:]
        context.user_data['transport_type'] = short_transport_type
        bot = query.get_bot()
        await query.answer('')
    else:
        short_transport_type = context.user_data['transport_type']
        bot = update.message.get_bot()
        chat_id = update.message.chat_id

    lang = 'it' if update.effective_user.language_code == 'it' else 'en'
    trans = gettext.translation('messages', localedir, languages=[lang])
    _ = trans.gettext

    transport_types = {
        'aut': _('aut'),
        'nav': _('nav')
    }

    transport_type = transport_types[short_transport_type]
    position = list(transport_types.keys()).index(short_transport_type)
    other_short_transport_type = list(transport_types.keys())[1 - position]
    other_transport_type = transport_types[other_short_transport_type]

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(_('change_service') % other_transport_type,
                             callback_data=f'1{other_short_transport_type}')
    ]])

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(_('service_selected') % transport_type, reply_markup=keyboard)
    else:
        await bot.send_message(chat_id, _('service_selected') % transport_type, reply_markup=keyboard)

    if send_second_message:
        if command == 'fermata':
            reply_keyboard = [[KeyboardButton(_('send_location'), request_location=True)]]
            reply_keyboard_markup = ReplyKeyboardMarkup(
                reply_keyboard, one_time_keyboard=True, resize_keyboard=True
            )
        else:
            reply_keyboard_markup = ReplyKeyboardRemove()

        if command == 'fermata':
            text = _('insert_stop')
        else:
            text = _('insert_line')
        await bot.send_message(chat_id, text, reply_markup=reply_keyboard_markup)

    if command == 'fermata':
        return SEARCH_STOP

    return SEARCH_LINE


async def specify_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await specify(update, context, 'fermata')


async def search_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = 'it' if update.effective_user.language_code == 'it' else 'en'
    trans = gettext.translation('messages', localedir, languages=[lang])
    _ = trans.gettext

    message = update.message

    if context.user_data['transport_type'] == 'aut':
        db_file = thismodule.aut_db_con
    else:
        db_file = thismodule.nav_db_con

    if message.location:
        lat = message.location.latitude
        lon = message.location.longitude
        stops_clusters = db_file.search_stops(lat=lat, lon=lon)
    else:
        stops_clusters = db_file.search_stops(name=message.text)

    if not stops_clusters:
        await update.message.reply_text(_('stop_not_found'))
        return SEARCH_STOP

    buttons = [[InlineKeyboardButton(cluster_name, callback_data=f'S{cluster_id}')]
               for cluster_id, cluster_name in stops_clusters]

    await update.message.reply_text(
        _('choose_stop'),
        reply_markup=InlineKeyboardMarkup(
            buttons
        )
    )

    return SHOW_STOP


async def send_stop_times(_, lang, con, stop_times_filter, chat_id, message_id, bot: Bot,
                          context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['query_data'] = stop_times_filter.query_data()

    if not message_id:
        await bot.send_message(chat_id, _('here_times'), disable_notification=True,
                               reply_markup=ReplyKeyboardMarkup([[_('minus_day'), _('plus_day')]],
                                                                resize_keyboard=True))

    stop_times_filter.lines = context.user_data.get('lines')
    service_ids = context.user_data.get('service_ids')
    stop_ids = context.user_data.get('stop_ids')
    results, service_ids, stop_ids = stop_times_filter.get_times(con, service_ids, stop_ids)
    context.user_data['lines'] = stop_times_filter.lines
    context.user_data['service_ids'] = service_ids
    context.user_data['stop_ids'] = stop_ids

    text, reply_markup = stop_times_filter.format_times_text(results, _, lang)

    if not message_id:
        await bot.send_message(chat_id, text=text, reply_markup=reply_markup, parse_mode='HTML')
        return SHOW_STOP

    await bot.edit_message_text(text, chat_id, message_id, reply_markup=reply_markup, parse_mode='HTML')
    return SHOW_STOP


async def show_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.user_data['transport_type'] == 'aut':
        con = thismodule.aut_db_con.con
    else:
        con = thismodule.nav_db_con.con
    lang = 'it' if update.effective_user.language_code == 'it' else 'en'
    trans = gettext.translation('messages', localedir, languages=[lang])
    _ = trans.gettext

    first_message = False

    now = datetime.now() - timedelta(minutes=5)

    message_id = None

    if update.callback_query:
        query = update.callback_query

        if query.data[0] == 'R':
            trip_id, day_raw, stop_sequence, line = query.data[1:].split('/')
            day = datetime.strptime(day_raw, '%Y%m%d').date()

            results = get_stops_from_trip_id(trip_id, con, stop_sequence)

            text = StopTimesFilter(day=day, line=line, start_time='').title(_, lang)

            for result in results:
                stop_id, stop_name, time_raw = result
                time_format = time_25_to_1(time_raw).isoformat(timespec="minutes")
                text += f'\n{time_format} {stop_name}'

            await query.answer('')
            reply_markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton(_('back'), callback_data=context.user_data['query_data'])]])
            await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode='HTML')
            return SHOW_STOP

        if query.data[0] == 'S':
            cluster_id = query.data[1:]
            stop_times_filter = StopTimesFilter(cluster_id, now.date(), '', now.time())
            first_message = True
        else:
            logger.info("Query data %s", query.data)
            stop_times_filter = StopTimesFilter(query_data=query.data)
            message_id = query.message.message_id
        chat_id = update.callback_query.message.chat_id
        bot = update.callback_query.get_bot()
        await query.answer('')
    else:
        if update.message.text == _('minus_day') or update.message.text == _('plus_day'):
            del context.user_data['lines']
            del context.user_data['service_ids']
            stop_times_filter = StopTimesFilter(query_data=context.user_data['query_data'])
            if update.message.text == _('minus_day'):
                stop_times_filter.day -= timedelta(days=1)
            else:
                stop_times_filter.day += timedelta(days=1)
            stop_times_filter.start_time = ''
            stop_times_filter.offset_times = 0

        else:
            stop_id = re.search(r'\d+', update.message.text).group(0)
            stop_times_filter = StopTimesFilter(stop_id, now.date(), '', now.time())
            first_message = True
        chat_id = update.message.chat_id
        bot = update.message.get_bot()

    return await send_stop_times(_, lang, con, stop_times_filter, chat_id, message_id, bot, context)


async def specify_line(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await specify(update, context, 'linea')


async def search_line(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.user_data['transport_type'] == 'aut':
        con = thismodule.aut_db_con.con
    else:
        con = thismodule.nav_db_con.con

    lang = 'it' if update.effective_user.language_code == 'it' else 'en'
    trans = gettext.translation('messages', localedir, languages=[lang])
    _ = trans.gettext

    today = datetime.now().date()
    service_ids = get_active_service_ids(today, con)

    lines = search_lines(update.message.text, service_ids, con)

    inline_markup = InlineKeyboardMarkup([[InlineKeyboardButton(line[2], callback_data=line[0])] for line in lines])

    await update.message.reply_text(_('choose_line'), reply_markup=inline_markup)

    return SHOW_LINE


async def show_line(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.user_data['transport_type'] == 'aut':
        con = thismodule.aut_db_con.con
    else:
        con = thismodule.nav_db_con.con

    lang = 'it' if update.effective_user.language_code == 'it' else 'en'
    trans = gettext.translation('messages', localedir, languages=[lang])
    _ = trans.gettext

    query = update.callback_query

    trip_id = query.data

    stops = get_stops_from_trip_id(trip_id, con)

    text = _('stops') + ':\n'

    for stop in stops:
        text += f'\n/{stop[0]} {stop[1]}'

    await query.answer('')
    await query.edit_message_text(text=text)

    return SHOW_STOP


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop('query_data', None)
    context.user_data.pop('lines', None)
    context.user_data.pop('service_ids', None)
    context.user_data.pop('stop_ids', None)

    lang = 'it' if update.effective_user.language_code == 'it' else 'en'
    trans = gettext.translation('messages', localedir, languages=[lang])
    _ = trans.gettext

    await update.message.reply_text(_('cancel') + "\n\n" + _('home') % (_('stop'), _('line')), reply_markup=ReplyKeyboardRemove())

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

    application = Application.builder().token(config['TOKEN']).persistence(persistence=SQLitePersistence()).build()

    langs = [f for f in os.listdir(localedir) if os.path.isdir(os.path.join(localedir, f))]
    default_lang = 'en'

    for lang in langs:
        trans = gettext.translation('messages', localedir, languages=[lang])
        _ = trans.gettext
        language_code = lang if lang != default_lang else ''
        r = requests.post(f'https://api.telegram.org/bot{config["TOKEN"]}/setMyCommands', json={
            'commands': [
                {'command': _('stop'), 'description': _('search_by_stop')},
                {'command': _('line'), 'description': _('search_by_line')}
            ],
            'language_code': language_code
        })

    conv_handler = ConversationHandler(
        name='orari',
        entry_points=[MessageHandler(filters.Regex(r'^\/[a-z]+$'), choose_service)],
        states={
            SPECIFY_STOP: [CallbackQueryHandler(specify_stop)],
            SEARCH_STOP: [
                MessageHandler((filters.TEXT | filters.LOCATION) & (~filters.COMMAND), search_stop),
                CallbackQueryHandler(specify_stop)
            ],
            SPECIFY_LINE: [CallbackQueryHandler(specify_line)],
            SEARCH_LINE: [
                MessageHandler(filters.TEXT & (~filters.COMMAND), search_line),
                CallbackQueryHandler(specify_line)
            ],
            SHOW_LINE: [CallbackQueryHandler(show_line)],
            SHOW_STOP: [
                MessageHandler(filters.Regex(r'(?:\/|\()\d+'), show_stop),
                CallbackQueryHandler(show_stop),
                MessageHandler(filters.Regex(r'^\-|\+1[a-z]$'), show_stop)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel), MessageHandler(filters.Regex(r'^\/[a-z]+$'), choose_service)],
        persistent=True
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler)

    if DEV:
        application.run_polling()
    else:
        application.run_webhook(listen='0.0.0.0', port=443, secret_token=config['SECRET_TOKEN'],
                                webhook_url=config['WEBHOOK_URL'], key=os.path.join(parent_dir, 'private.key'),
                                cert=os.path.join(parent_dir, 'cert.pem'))
