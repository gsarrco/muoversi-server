import gettext
import logging
import os
import sys
from datetime import timedelta, datetime, date

import requests
from babel.dates import format_date
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, \
    ReplyKeyboardRemove, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters, CallbackQueryHandler, )
from telegram.ext import ContextTypes

from config import config
from server.base import Source
from .persistence import SQLitePersistence
from .routes import get_routes
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

SEARCH_STOP, SPECIFY_LINE, SEARCH_LINE, SHOW_LINE, SHOW_STOP = range(5)

localedir = os.path.join(parent_dir, 'locales')


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
    await update.message.reply_text(_('welcome') + "\n\n" + _('home') % (_('stop'), _('line')),
                                    disable_notification=True)


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

    command_text = update.message.text[1:]

    if command_text == 'fermata' or command_text == 'stop':
        command = 'fermata'
    elif command_text == 'linea' or command_text == 'line':
        command = 'linea'
    else:
        return ConversationHandler.END

    clean_user_data(context)

    if command == 'fermata':
        reply_keyboard = [[KeyboardButton(_('send_location'), request_location=True)]]
        reply_keyboard_markup = ReplyKeyboardMarkup(
            reply_keyboard, resize_keyboard=True, is_persistent=True
        )
        await update.message.reply_text(_('insert_stop'), reply_markup=reply_keyboard_markup, parse_mode='HTML',
                                        disable_notification=True)
        return SEARCH_STOP

    if context.user_data.get('transport_type'):
        return await specify_line(update, context)

    inline_keyboard = [[]]

    for source in thismodule.sources:
        inline_keyboard[0].append(InlineKeyboardButton(_(source), callback_data="T0" + source))

    await update.message.reply_text(
        _('choose_service'),
        reply_markup=InlineKeyboardMarkup(inline_keyboard),
        disable_notification=True
    )

    return SPECIFY_LINE


async def specify_line(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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
        await bot.send_message(chat_id, _('service_selected') % transport_type, reply_markup=keyboard,
                               disable_notification=True)

    if send_second_message:
        await bot.send_message(chat_id, _('insert_line'), reply_markup=ReplyKeyboardRemove(), disable_notification=True)

    return SEARCH_LINE


async def search_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = 'it' if update.effective_user.language_code == 'it' else 'en'
    trans = gettext.translation('messages', localedir, languages=[lang])
    _ = trans.gettext

    db_file: Source = thismodule.sources[context.user_data.get('transport_type', 'aut')]

    limit = 4

    saved_dep_stop_ids = 'dep_stop_ids' not in context.user_data

    if update.callback_query:
        text, lat, lon, page = update.callback_query.data[1:].split('/')
        page = int(page)
    else:
        text, lat, lon, page = '', '', '', 1
        message = update.message
        if message.location:
            lat = message.location.latitude
            lon = message.location.longitude
        else:
            text = message.text

    if lat == '' and lon == '':
        stops_clusters, count = db_file.search_stops(name=text, all_sources=saved_dep_stop_ids, page=page, limit=limit)
    else:
        stops_clusters, count = db_file.search_stops(lat=lat, lon=lon, all_sources=saved_dep_stop_ids, page=page,
                                                     limit=limit)

    if not stops_clusters:
        await update.message.reply_text(_('stop_not_found'), disable_notification=True)
        return SEARCH_STOP

    buttons = [[InlineKeyboardButton(f'{cluster.name} {thismodule.sources[cluster.source].emoji}',
                                     callback_data=f'S{cluster.id}-{cluster.source}')]
               for cluster in stops_clusters]

    paging_buttons = []
    if page > 1:
        paging_buttons.append(InlineKeyboardButton('<', callback_data=f'F{text}/{lat}/{lon}/{page - 1}'))
    if page * limit < count:
        paging_buttons.append(InlineKeyboardButton('>', callback_data=f'F{text}/{lat}/{lon}/{page + 1}'))

    if paging_buttons:
        buttons.append(paging_buttons)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            _('choose_stop'),
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    else:
        await update.message.reply_text(
            _('choose_stop'),
            reply_markup=InlineKeyboardMarkup(buttons),
            disable_notification=True
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

    # add service_ids to Source instance, this way it can be accessed from get_stop_times
    db_file.service_ids = context.bot_data.setdefault('service_ids', {}).setdefault(db_file.name, {})

    results = stop_times_filter.get_times(db_file)

    context.bot_data['service_ids'][db_file.name] = db_file.service_ids

    context.user_data['lines'] = stop_times_filter.lines

    text, reply_markup = stop_times_filter.format_times_text(results, _, lang)

    if message_id:
        await bot.edit_message_text(text, chat_id, message_id, reply_markup=reply_markup, parse_mode='HTML')
    else:
        await bot.send_message(chat_id, text=text, reply_markup=reply_markup, parse_mode='HTML',
                               disable_notification=True)

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
    lang = 'it' if update.effective_user.language_code == 'it' else 'en'
    trans = gettext.translation('messages', localedir, languages=[lang])
    _ = trans.gettext

    now = datetime.now()

    text = update.message.text if update.message else update.callback_query.data

    message_id = None

    if update.callback_query:
        message_id = update.callback_query.message.message_id

    stop_ref, line = text[1:].split('/') if '/' in text else (text[1:], '')
    if '-' in stop_ref:
        stop_ref, source_name = stop_ref.split('-')
        db_file: Source = thismodule.sources[source_name]
        context.user_data['transport_type'] = source_name
    else:
        db_file = thismodule.sources[context.user_data['transport_type']]

    station = db_file.get_stop_from_ref(stop_ref)
    cluster_name = station.name
    stop_ids = ','.join([stop.id for stop in station.stops])
    saved_dep_stop_ids = context.user_data.get('dep_stop_ids')
    saved_dep_cluster_name = context.user_data.get('dep_cluster_name')

    if saved_dep_stop_ids:
        stop_times_filter = StopTimesFilter(context, db_file, saved_dep_stop_ids, now.date(), line, now.time(),
                                            arr_stop_ids=stop_ids,
                                            arr_cluster_name=cluster_name, dep_cluster_name=saved_dep_cluster_name,
                                            first_time=True)
        context.user_data['arr_stop_ids'] = stop_ids
        context.user_data['arr_cluster_name'] = cluster_name
    else:
        stop_times_filter = StopTimesFilter(context, db_file, stop_ids, now.date(), line, now.time(),
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


async def trip_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    source: Source = thismodule.sources[context.user_data['transport_type']]
    lang = 'it' if update.effective_user.language_code == 'it' else 'en'
    trans = gettext.translation('messages', localedir, languages=[lang])
    _ = trans.gettext
    query_data = context.user_data['query_data']
    dep_stop_ids = context.user_data['dep_stop_ids']
    dep_cluster_name = context.user_data['dep_cluster_name']
    arr_stop_ids = context.user_data.get('arr_stop_ids')
    arr_cluster_name = context.user_data.get('arr_cluster_name')

    stop_times_filter = StopTimesFilter(context, source, query_data=query_data, dep_stop_ids=dep_stop_ids,
                                        dep_cluster_name=dep_cluster_name, arr_stop_ids=arr_stop_ids,
                                        arr_cluster_name=arr_cluster_name)
    if update.message:
        text, all_stops = update.message.text, False
    else:
        text, all_stops = update.callback_query.data, True
    trip_id = text[1:]
    results = source.get_stops_from_trip_id(trip_id, stop_times_filter.day)

    line = results[0].route_name
    text = '<b>' + format_date(stop_times_filter.day, 'EEEE d MMMM', locale=lang) + ' - ' + _(
        'line') + ' ' + line + f' {trip_id}</b>'

    dep_stop_index = 0
    arr_stop_index = len(results) - 1
    if not all_stops:
        dep_stop_ids = stop_times_filter.dep_stop_ids.split(',')
        try:
            dep_stop_index = next(i for i, v in enumerate(results) if v.station.id in dep_stop_ids)
        except StopIteration:
            logger.warning('No departure stop found')
        if arr_cluster_name:
            arr_stop_ids = stop_times_filter.arr_stop_ids.split(',')
            try:
                arr_stop_index = dep_stop_index + next(
                    i for i, v in enumerate(results[dep_stop_index:]) if str(v.station.id) in arr_stop_ids)
            except StopIteration:
                logger.warning('No arrival stop found')

    platform_text = _(f'{source.name}_platform')

    are_dep_and_arr_times_equal = all(
        result.arr_time == result.dep_time for result in results[dep_stop_index:arr_stop_index + 1])

    for i, result in enumerate(results[dep_stop_index:arr_stop_index + 1]):
        arr_time = result.arr_time.strftime('%H:%M') if result.arr_time else ''
        dep_time = result.dep_time.strftime('%H:%M') if result.dep_time else ''

        if are_dep_and_arr_times_equal:
            text += f'\n<b>{arr_time}</b> {result.station.station.name}'
        else:
            if i == 0:
                text += f'\n{result.station.station.name} <b>{dep_time}</b>'
            elif i == arr_stop_index:
                text += f'\n<b>{arr_time}</b> {result.station.station.name}'
            else:
                text += f'\n<b>{arr_time}</b> {result.station.station.name} <b>{dep_time}</b>'

        if result.platform:
            text += f' ({platform_text} {result.platform})'

    buttons = [InlineKeyboardButton(_('back'), callback_data=context.user_data['query_data'])]

    if not all_stops:
        buttons.append(InlineKeyboardButton(_('all_stops'), callback_data=f'M{trip_id}'))

    reply_markup = InlineKeyboardMarkup([buttons])
    if update.message:
        await update.message.reply_text(text=text, reply_markup=reply_markup, parse_mode='HTML',
                                        disable_notification=True)
    else:
        await update.callback_query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode='HTML')
    return SHOW_STOP


async def search_line(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db_file: Source = thismodule.sources[context.user_data['transport_type']]

    lang = 'it' if update.effective_user.language_code == 'it' else 'en'
    trans = gettext.translation('messages', localedir, languages=[lang])
    _ = trans.gettext

    try:
        lines = db_file.search_lines(update.message.text)
    except NotImplementedError:
        await update.message.reply_text(_('not_implemented'), disable_notification=True)
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(line[2], callback_data=f'L{line[0]}/{line[1]}')] for line in lines]
    inline_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(_('choose_line'), reply_markup=inline_markup, disable_notification=True)

    return SHOW_LINE


async def show_line(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    source: Source = thismodule.sources[context.user_data['transport_type']]
    lang = 'it' if update.effective_user.language_code == 'it' else 'en'
    trans = gettext.translation('messages', localedir, languages=[lang])
    _ = trans.gettext

    query = update.callback_query

    trip_id, line = query.data[1:].split('/')

    day = date.today()
    stops = source.get_stops_from_trip_id(trip_id, day)

    text = _('stops') + ':\n'

    inline_buttons = []

    for stop in stops:
        station = stop.station.station
        stop_id = station.id
        stop_name = station.name
        inline_buttons.append([InlineKeyboardButton(stop_name, callback_data=f'S{stop_id}/{line}')])

    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(inline_buttons))
    await query.answer('')

    return SHOW_STOP


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    clean_user_data(context)

    lang = 'it' if update.effective_user.language_code == 'it' else 'en'
    trans = gettext.translation('messages', localedir, languages=[lang])
    _ = trans.gettext

    await update.message.reply_text(_('cancel') + "\n\n" + _('home') % (_('stop'), _('line')),
                                    reply_markup=ReplyKeyboardRemove(), disable_notification=True)

    return ConversationHandler.END


async def setup(config, sources):
    DEV = config.get('DEV', False)

    thismodule.sources = sources

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
            SEARCH_STOP: [
                MessageHandler((filters.TEXT | filters.LOCATION) & (~filters.COMMAND), search_stop)
            ],
            SPECIFY_LINE: [CallbackQueryHandler(specify_line, r'^T')],
            SEARCH_LINE: [
                MessageHandler(filters.TEXT & (~filters.COMMAND), search_line),
                CallbackQueryHandler(specify_line, r'^T')
            ],
            SHOW_LINE: [CallbackQueryHandler(show_line, r'^L')],
            SHOW_STOP: [
                CallbackQueryHandler(filter_show_stop, r'^Q'),
                MessageHandler(filters.Regex(r'^\/[0-9]+$'), trip_view),
                CallbackQueryHandler(trip_view, r'^M'),
                CallbackQueryHandler(show_stop_from_id, r'^S'),
                MessageHandler(filters.Regex(r'^\-|\+1[a-z]$'), change_day_show_stop),
                MessageHandler((filters.TEXT | filters.LOCATION) & (~filters.COMMAND), search_stop),
                CallbackQueryHandler(search_stop, r'^F')
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel), MessageHandler(filters.Regex(r'^\/[a-z]+$'), choose_service)],
        persistent=True
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Regex(r'^\/announce '), announce))
    application.add_handler(conv_handler)

    webhook_url = config['WEBHOOK_URL'] + '/tg_bot_webhook'
    bot: Bot = application.bot

    if DEV:
        await bot.set_webhook(webhook_url, os.path.join(parent_dir, 'cert.pem'), secret_token=config['SECRET_TOKEN'])
    else:
        await bot.set_webhook(webhook_url, secret_token=config['SECRET_TOKEN'])

    return application, get_routes(application)
