import logging
from datetime import datetime, timedelta, time, date
from sqlite3 import Connection

from babel.dates import format_date
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from MuoVErsi.helpers import time_25_to_1, split_list, times_groups, get_active_service_ids, get_lines_from_stops

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

LIMIT = 12
MAX_CHOICE_BUTTONS_PER_ROW = LIMIT // 2


class StopTimesFilter:
    def __init__(self, stop_id=None, day=None, line=None, start_time=None, offset_times=0, offset_lines=0,
                 query_data=None):

        if query_data:
            stop_id, day_raw, line, start_time_raw, offset_times, offset_lines = \
                query_data.split('/')
            day = datetime.strptime(day_raw, '%Y%m%d').date()
            start_time = time.fromisoformat(start_time_raw) if start_time_raw != '' else ''

        self.stop_id = stop_id
        self.day = day
        self.line = line
        self.start_time = start_time
        self.offset_times = int(offset_times)
        self.offset_lines = int(offset_lines)
        self.lines = None

    def query_data(self, **new_params):
        original_params = self.__dict__
        to_print = {k: new_params[k] if k in new_params else original_params[k] for k in set(original_params)}
        # order dict by key
        to_print = {k: to_print[k] for k in sorted(to_print)}
        to_print['day'] = to_print['day'].strftime('%Y%m%d')
        to_print['start_time'] = to_print['start_time'].isoformat(timespec='minutes') if to_print['start_time'] != '' else ''

        result = f'{to_print["stop_id"]}/{to_print["day"]}/{to_print["line"]}/' \
                 f'{to_print["start_time"]}/{to_print["offset_times"]}/{to_print["offset_lines"]}'
        logger.info(result)
        return result

    def save_query_data(self, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['query_data'] = self.query_data()
        prev_day = self.day - timedelta(days=1)
        context.user_data['-1g'] = self.query_data(day=prev_day, start_time='')
        next_day = self.day + timedelta(days=1)
        context.user_data['+1g'] = self.query_data(day=next_day, start_time='')

    def title(self):
        text = '<b>' + format_date(self.day, format='full', locale='it')

        start_time = self.start_time

        if start_time != '':
            text += f' - {start_time.strftime("%H:%M")}'

        if self.line != '':
            text += f' - linea {self.line}'
        return text + '</b>'

    def inline_button(self, text: str, **new_params):
        return InlineKeyboardButton(text, callback_data=self.query_data(**new_params))

    def get_times(self, con: Connection, service_ids, stop_ids):
        day, stop_id, line, start_time = self.day, self.stop_id, self.line, \
            self.start_time

        if service_ids is None:
            service_ids = get_active_service_ids(day, con)

        route = 'AND route_short_name = ?' if line != '' else ''
        departure_time = 'AND departure_time >= ?' if start_time != '' else ''

        if stop_ids is None:
            results = con.execute('SELECT stop_id FROM stops_stops_clusters WHERE stop_cluster_id = ?',
                                  (stop_id,)).fetchall()
            stop_ids = [result[0] for result in results]

        query = """SELECT departure_time, route_short_name, trip_headsign, trips.trip_id, stop_sequence
                    FROM stop_times
                             INNER JOIN trips ON stop_times.trip_id = trips.trip_id
                             INNER JOIN routes ON trips.route_id = routes.route_id
                    WHERE stop_times.stop_id in ({stop_id})
                      AND trips.service_id in ({seq})
                      AND pickup_type = 0
                      {route}
                      {departure_time}
                    ORDER BY departure_time, route_short_name, trip_headsign
                    LIMIT ? OFFSET ?
                    """.format(
            seq=','.join(['?'] * len(service_ids)), stop_id=','.join(['?'] * len(stop_ids)), route=route,
            departure_time=departure_time)

        params = (*stop_ids, *service_ids)

        if line != '':
            params += (line,)

        if start_time != '':
            params += (start_time.strftime('%H:%M'),)

        params += (LIMIT, self.offset_times)

        cur = con.cursor()
        results = cur.execute(query, params).fetchall()

        if self.lines is None:
            self.lines = get_lines_from_stops(service_ids, stop_ids, con)

        return results, service_ids, stop_ids

    def format_times_text(self, results):
        text = f'{self.title()}'

        if self.day < date.today():
            text += f'\nNon possiamo mostrare orari di giornate passate. Torna alla giornata odierna o a una futura.'
            return text, None

        results_len = len(results)

        if results_len == 0:
            text += '\nNessun orario trovato per questi filtri.'

        choice_buttons = []
        for i, result in enumerate(results):
            time_raw, line, headsign, trip_id, stop_sequence = result
            time_format = time_25_to_1(time_raw).isoformat(timespec="minutes")
            text += f'\n{i + 1}. {time_format} {line} {headsign}'
            callback_data = f'R{trip_id}/{self.day.strftime("%Y%m%d")}/{stop_sequence}/{line}'
            choice_buttons.append(InlineKeyboardButton(f'{i + 1}', callback_data=callback_data))

        keyboard = []
        len_choice_buttons = len(choice_buttons)
        if len_choice_buttons > MAX_CHOICE_BUTTONS_PER_ROW:
            keyboard = split_list(choice_buttons)
        elif len_choice_buttons > 0:
            keyboard.append([button for button in choice_buttons])

        paging_buttons = []

        # prev/next page buttons
        if results_len > 0:
            if self.offset_times > 0:
                paging_buttons.append(self.inline_button('<<', offset_times=self.offset_times - LIMIT))
            if results_len == LIMIT:
                paging_buttons.append(self.inline_button('>>', offset_times=self.offset_times + LIMIT))

        keyboard.append(paging_buttons)

        # Lines buttons
        if self.line == '':
            lines = self.lines

            limit = 4 if 0 < self.offset_lines < len(lines) - 5 else 5
            prev_limit = 5 if self.offset_lines == 5 else 4

            line_buttons = [self.inline_button(line, line=line, offset_times=0) for line in
                            lines[self.offset_lines:self.offset_lines + limit]]
            if self.offset_lines > 0:
                line_buttons.insert(0, self.inline_button('<<', offset_lines=self.offset_lines - prev_limit))
            if self.offset_lines + 5 < len(lines):
                line_buttons.append(self.inline_button('>>', offset_lines=self.offset_lines + limit))
            len_line_buttons = len(line_buttons)
            if len_line_buttons > 1:
                keyboard.append(line_buttons)
        else:
            keyboard.append([self.inline_button('Tutte le linee', line='', offset_times=0)])

        reply_markup = InlineKeyboardMarkup(keyboard)
        return text, reply_markup
