import gettext
import gettext
import logging
import os
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

from .helpers import time_25_to_1, get_stops_from_trip_id
from .persistence import SQLitePersistence
from .sources.GTFS import GTFS
from .sources.base import Source
from .sources.trenitalia import Trenitalia
from .stop_times_filter import StopTimesFilter

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

current_dir = os.path.abspath(os.path.dirname(__file__))
parent_dir = os.path.abspath(current_dir + "/../")
thismodule = sys.modules[__name__]
thismodule.sources = {}
thismodule.persistence = SQLitePersistence()

SPECIFY_STOP, SEARCH_STOP, SPECIFY_LINE, SEARCH_LINE, SHOW_LINE, SHOW_STOP = range(6)

localedir = os.path.join(parent_dir, 'locales')

config_path = os.path.join(parent_dir, 'config.yaml')
with open(config_path, 'r') as config_file:
    try:
        config = yaml.safe_load(config_file)
        logger.info(config)
    except yaml.YAMLError as err:
        logger.error(err)


def clean_user_data(context, keep_transport_type=True):
    context.user_data.pop('query_data', None)
    context.user_data.pop('lines', None)
    context.user_data.pop('dep_stop_ids', None)
    context.user_data.pop('arr_stop_ids', None)
    context.user_data.pop('dep_cluster_name', None)
    context.user_data.pop('arr_cluster_name', None)
    if not keep_transport_type:
        context.user_data.pop('transport_type', None)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = 'it' if update.effective_user.language_code == 'it' else 'en'
    trans = gettext.translation('messages', localedir, languages=[lang])
    _ = trans.gettext
    clean_user_data(context, False)
    await update.message.reply_text(_('welcome') + "\n\n" + _('home') % (_('stop'), _('line')))


async def announce(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if config.get('ADMIN_TG_ID') != update.effective_user.id:
        return

    persistence: SQLitePersistence = thismodule.persistence
    user_ids = persistence.get_all_users()
    text = update.message.text[10:]
    for user_id in user_ids:
        try:
            await context.bot.send_message(user_id, text, parse_mode='HTML', disable_notification=True)
        except Exception as e:
            logger.error(e)


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

    clean_user_data(context)

    if context.user_data.get('transport_type'):
        return await specify(update, context, command)

    inline_keyboard = [[]]

    for source in thismodule.sources:
        inline_keyboard[0].append(InlineKeyboardButton(_(source), callback_data="T0" + source))

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
        if query.data[1] == '1':
            send_second_message = False
        chat_id = query.message.chat_id
        short_transport_type = query.data[2:]
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

    others_sources = [source for source in thismodule.sources if source != short_transport_type]

    inline_keyboard = [[]]

    for source in others_sources:
        inline_keyboard[0].append(InlineKeyboardButton(_('change_service') % _(source), callback_data="T1" + source))

    transport_type = _(short_transport_type)

    keyboard = InlineKeyboardMarkup(inline_keyboard)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(_('service_selected') % transport_type, reply_markup=keyboard)
    else:
        await bot.send_message(chat_id, _('service_selected') % transport_type, reply_markup=keyboard)

    if send_second_message:
        if command == 'fermata':
            reply_keyboard = [[KeyboardButton(_('send_location'), request_location=True)]]
            reply_keyboard_markup = ReplyKeyboardMarkup(
                reply_keyboard, resize_keyboard=True, is_persistent=True
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

    db_file: Source = thismodule.sources[context.user_data['transport_type']]

    if message.location:
        lat = message.location.latitude
        lon = message.location.longitude
        stops_clusters = db_file.search_stops(lat=lat, lon=lon)
    else:
        stops_clusters = db_file.search_stops(name=message.text)

    if not stops_clusters:
        await update.message.reply_text(_('stop_not_found'))
        return SEARCH_STOP

    buttons = [[InlineKeyboardButton(cluster.name, callback_data=f'S{cluster.ref}')]
               for cluster in stops_clusters]

    await update.message.reply_text(
        _('choose_stop'),
        reply_markup=InlineKeyboardMarkup(
            buttons
        )
    )

    return SHOW_STOP


async def send_stop_times(_, lang, db_file: Source, stop_times_filter: StopTimesFilter, chat_id, message_id, bot: Bot,
                          context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['query_data'] = stop_times_filter.query_data()

    if stop_times_filter.first_time:
        context.user_data.pop('lines', None)

    stop_times_filter.lines = context.user_data.get('lines')

    if context.user_data.get('day') != stop_times_filter.day.isoformat():
        context.user_data['day'] = stop_times_filter.day.isoformat()

    results = stop_times_filter.get_times(db_file)

    context.user_data['lines'] = stop_times_filter.lines

    text, reply_markup = stop_times_filter.format_times_text(results, _, lang)

    if message_id:
        await bot.edit_message_text(text, chat_id, message_id, reply_markup=reply_markup, parse_mode='HTML')
    else:
        await bot.send_message(chat_id, text=text, reply_markup=reply_markup, parse_mode='HTML')

    if stop_times_filter.first_time:
        if stop_times_filter.arr_stop_ids:
            text = '<i>' + _('send_new_arr_stop') + '</i>'
        else:
            text = '<i>' + _('send_arr_stop') + '</i>'

        reply_keyboard = [[KeyboardButton(_('send_location'), request_location=True)]]
        reply_keyboard_markup = ReplyKeyboardMarkup(
            reply_keyboard, resize_keyboard=True, is_persistent=True
        )

        await bot.send_message(chat_id, text, disable_notification=True,
                               reply_markup=reply_keyboard_markup, parse_mode='HTML')

    return SHOW_STOP


async def change_day_show_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db_file = thismodule.sources[context.user_data['transport_type']]

    lang = 'it' if update.effective_user.language_code == 'it' else 'en'
    trans = gettext.translation('messages', localedir, languages=[lang])
    _ = trans.gettext

    del context.user_data['lines']
    dep_stop_ids = context.user_data.get('dep_stop_ids')
    arr_stop_ids = context.user_data.get('arr_stop_ids')
    dep_cluster_name = context.user_data.get('dep_cluster_name')
    arr_cluster_name = context.user_data.get('arr_cluster_name')
    stop_times_filter = StopTimesFilter(context, db_file, dep_stop_ids=dep_stop_ids,
                                        query_data=context.user_data['query_data'],
                                        arr_stop_ids=arr_stop_ids, dep_cluster_name=dep_cluster_name,
                                        arr_cluster_name=arr_cluster_name)
    if update.message.text == _('minus_day'):
        stop_times_filter.day -= timedelta(days=1)
    else:
        stop_times_filter.day += timedelta(days=1)
    stop_times_filter.start_time = ''
    stop_times_filter.offset_times = 0

    return await send_stop_times(_, lang, db_file, stop_times_filter, update.effective_chat.id, None, update.get_bot(),
                                 context)


async def show_stop_from_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db_file: Source = thismodule.sources[context.user_data['transport_type']]

    lang = 'it' if update.effective_user.language_code == 'it' else 'en'
    trans = gettext.translation('messages', localedir, languages=[lang])
    _ = trans.gettext

    now = datetime.now()

    text = update.message.text if update.message else update.callback_query.data

    message_id = None

    if update.callback_query:
        message_id = update.callback_query.message.message_id

    stop_ref = text[1:]
    stop = db_file.get_stop_from_ref(stop_ref)
    cluster_name = stop.name
    stop_ids = stop.ids
    saved_dep_stop_ids = context.user_data.get('dep_stop_ids')
    saved_dep_cluster_name = context.user_data.get('dep_cluster_name')

    if saved_dep_stop_ids:
        stop_times_filter = StopTimesFilter(context, db_file, saved_dep_stop_ids, now.date(), '', now.time(),
                                            arr_stop_ids=stop_ids,
                                            arr_cluster_name=cluster_name, dep_cluster_name=saved_dep_cluster_name,
                                            first_time=True)
        context.user_data['arr_stop_ids'] = stop_ids
        context.user_data['arr_cluster_name'] = cluster_name
    else:
        stop_times_filter = StopTimesFilter(context, db_file, stop_ids, now.date(), '', now.time(),
                                            dep_cluster_name=cluster_name,
                                            first_time=True)
        context.user_data['dep_stop_ids'] = stop_ids
        context.user_data['dep_cluster_name'] = cluster_name

    new_state = await send_stop_times(_, lang, db_file, stop_times_filter, update.effective_chat.id,
                                      message_id, update.get_bot(), context)

    if update.callback_query:
        await update.callback_query.answer()

    return new_state


async def filter_show_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db_file = thismodule.sources[context.user_data['transport_type']]

    lang = 'it' if update.effective_user.language_code == 'it' else 'en'
    trans = gettext.translation('messages', localedir, languages=[lang])
    _ = trans.gettext

    query = update.callback_query
    logger.info("Query data %s", query.data)
    dep_stop_ids = context.user_data.get('dep_stop_ids')
    arr_stop_ids = context.user_data.get('arr_stop_ids')
    dep_cluster_name = context.user_data.get('dep_cluster_name')
    arr_cluster_name = context.user_data.get('arr_cluster_name')
    stop_times_filter = StopTimesFilter(context, db_file, dep_stop_ids=dep_stop_ids, query_data=query.data,
                                        arr_stop_ids=arr_stop_ids,
                                        dep_cluster_name=dep_cluster_name, arr_cluster_name=arr_cluster_name)
    message_id = query.message.message_id

    chat_id = update.callback_query.message.chat_id
    bot = update.get_bot()

    new_state = await send_stop_times(_, lang, db_file, stop_times_filter, chat_id, message_id, bot, context)

    await query.answer('')

    return new_state


async def ride_view_show_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db_file = thismodule.sources[context.user_data['transport_type']]
    con = db_file.con
    lang = 'it' if update.effective_user.language_code == 'it' else 'en'
    trans = gettext.translation('messages', localedir, languages=[lang])
    _ = trans.gettext

    query = update.callback_query

    trip_id, day_raw, stop_sequence, line = query.data[1:].split('/')
    day = datetime.strptime(day_raw, '%Y%m%d').date()

    results = get_stops_from_trip_id(trip_id, con, stop_sequence)

    text = StopTimesFilter(context, db_file, day=day, line=line, start_time='').title(_, lang)

    for result in results:
        stop_id, stop_name, time_raw = result
        time_format = time_25_to_1(day, time_raw).isoformat(timespec="minutes")
        text += f'\n{time_format} {stop_name}'

    reply_markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton(_('back'), callback_data=context.user_data['query_data'])]])
    await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode='HTML')
    await query.answer('')
    return SHOW_STOP


async def specify_line(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await specify(update, context, 'linea')


async def search_line(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db_file: Source = thismodule.sources[context.user_data['transport_type']]

    lang = 'it' if update.effective_user.language_code == 'it' else 'en'
    trans = gettext.translation('messages', localedir, languages=[lang])
    _ = trans.gettext

    try:
        lines = db_file.search_lines(update.message.text, context=context)
    except NotImplementedError:
        await update.message.reply_text(_('not_implemented'))
        return ConversationHandler.END

    inline_markup = InlineKeyboardMarkup([[InlineKeyboardButton(line[2], callback_data=line[0])] for line in lines])

    await update.message.reply_text(_('choose_line'), reply_markup=inline_markup)

    return SHOW_LINE


async def show_line(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db_file = thismodule.sources[context.user_data['transport_type']]
    con = db_file.con
    lang = 'it' if update.effective_user.language_code == 'it' else 'en'
    trans = gettext.translation('messages', localedir, languages=[lang])
    _ = trans.gettext

    query = update.callback_query

    trip_id = query.data

    stops = get_stops_from_trip_id(trip_id, con)

    text = _('stops') + ':\n'

    for stop in stops:
        text += f'\n/{stop[0]} {stop[1]}'

    await query.edit_message_text(text=text)
    await query.answer('')

    return SHOW_STOP


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    clean_user_data(context)

    lang = 'it' if update.effective_user.language_code == 'it' else 'en'
    trans = gettext.translation('messages', localedir, languages=[lang])
    _ = trans.gettext

    await update.message.reply_text(_('cancel') + "\n\n" + _('home') % (_('stop'), _('line')), reply_markup=ReplyKeyboardRemove())

    return ConversationHandler.END


def main() -> None:
    DEV = config.get('DEV', False)

    PGUSER = config.get('PGUSER', None)
    PGPASSWORD = config.get('PGPASSWORD', None)
    PGHOST = config.get('PGHOST', None)
    PGPORT = config.get('PGPORT', 5432)
    PGDATABASE = config.get('PGDATABASE', None)

    thismodule.sources = {
        'aut': GTFS('automobilistico', dev=DEV),
        'nav': GTFS('navigazione', dev=DEV),
        'treni': Trenitalia(PGUSER, PGPASSWORD, PGHOST, PGPORT, PGDATABASE, dev=DEV)
    }

    application = Application.builder().token(config['TOKEN']).persistence(persistence=thismodule.persistence).build()

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
            SPECIFY_STOP: [CallbackQueryHandler(specify_stop, r'^T')],
            SEARCH_STOP: [
                MessageHandler((filters.TEXT | filters.LOCATION) & (~filters.COMMAND), search_stop),
                CallbackQueryHandler(specify_stop, r'^T'),
            ],
            SPECIFY_LINE: [CallbackQueryHandler(specify_line, r'^T')],
            SEARCH_LINE: [
                MessageHandler(filters.TEXT & (~filters.COMMAND), search_line),
                CallbackQueryHandler(specify_line, r'^T')
            ],
            SHOW_LINE: [CallbackQueryHandler(show_line)],
            SHOW_STOP: [
                MessageHandler(filters.Regex(r'(?:\/|\()\d+'), show_stop_from_id),
                CallbackQueryHandler(filter_show_stop, r'^Q'),
                CallbackQueryHandler(ride_view_show_stop, r'^R'),
                CallbackQueryHandler(show_stop_from_id, r'^S'),
                MessageHandler(filters.Regex(r'^\-|\+1[a-z]$'), change_day_show_stop),
                MessageHandler((filters.TEXT | filters.LOCATION) & (~filters.COMMAND), search_stop)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel), MessageHandler(filters.Regex(r'^\/[a-z]+$'), choose_service)],
        persistent=True
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Regex(r'^\/announce '), announce))
    application.add_handler(conv_handler)

    if DEV:
        application.run_polling()
    else:
        application.run_webhook(listen='0.0.0.0', port=443, secret_token=config['SECRET_TOKEN'],
                                webhook_url=config['WEBHOOK_URL'], key=os.path.join(parent_dir, 'private.key'),
                                cert=os.path.join(parent_dir, 'cert.pem'))
