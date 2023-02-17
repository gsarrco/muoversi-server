import logging
from datetime import datetime, timedelta, time, date
from sqlite3 import Connection

from babel.dates import format_date
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from MuoVErsi.helpers import get_time, split_list, times_groups, format_time, get_active_service_ids


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

LIMIT = 12
MAX_CHOICE_BUTTONS_PER_ROW = LIMIT // 2


class StopTimesFilter:
    def __init__(self, stop_id=None, day=None, line=None, start_time=None, end_time=None, direction='',
                 line_direction=0, offset_lines=0,
                 query_data=None):

        if query_data:
            stop_id, day_raw, line, start_time_raw, end_time_raw, direction, line_direction, offset_lines = \
                query_data.split('/')
            day = datetime.strptime(day_raw, '%Y-%m-%d').date()
            start_time = time.fromisoformat(start_time_raw) if start_time_raw != '' else ''
            end_time = time.fromisoformat(end_time_raw) if end_time_raw != '' else ''

        self.stop_id = stop_id
        self.day = day
        self.line = line
        self.start_time = start_time
        self.end_time = end_time
        self.direction = int(direction) if direction != '' else ''
        self.line_direction = int(line_direction)
        self.offset_lines = int(offset_lines)

    def query_data(self, **new_params):
        original_params = self.__dict__
        to_print = {k: new_params[k] if k in new_params else original_params[k] for k in set(original_params)}
        # order dict by key
        to_print = {k: to_print[k] for k in sorted(to_print)}
        to_print['day'] = to_print['day'].isoformat()
        if to_print['line_direction'] == 'switch':
            to_print['line_direction'] = 1 - self.line_direction

        result = f'{to_print["stop_id"]}/{to_print["day"]}/{to_print["line"]}/' \
               f'{to_print["start_time"]}/{to_print["end_time"]}/{to_print["direction"]}/{to_print["line_direction"]}/' \
                 f'{to_print["offset_lines"]}'
        logger.info(result)
        return result

    def save_query_data(self, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['query_data'] = self.query_data()
        prev_day = self.day - timedelta(days=1)
        context.user_data['-1g'] = self.query_data(day=prev_day, start_time='', end_time='', direction='')
        next_day = self.day + timedelta(days=1)
        context.user_data['+1g'] = self.query_data(day=next_day, start_time='', end_time='', direction='')

    def title(self):
        text = '<b>' + format_date(self.day, format='full', locale='it')

        start_time, end_time = self.start_time, self.end_time

        if start_time != '' and end_time == '':
            text += ' - dalle ' + start_time.strftime("%H:%M")
        if start_time == '' and end_time != '':
            text += ' - alle ' + end_time.strftime("%H:%M")
        if start_time != '' and end_time != '':
            text += f' - {start_time.strftime("%H:%M")}-{end_time.strftime("%H:%M")}'

        if self.line != '':
            text += f' - linea {self.line}'
        return text + '</b>'

    def inline_button(self, text: str, **new_params):
        return InlineKeyboardButton(text, callback_data=self.query_data(**new_params))

    def get_times(self, con: Connection):
        day, stop_id, line, start_time, end_time = self.day, self.stop_id, self.line, \
            self.start_time, self.end_time

        service_ids = get_active_service_ids(day, con)

        route = 'AND route_short_name = ?' if line != '' else ''

        if start_time == '':
            if day == date.today():
                start_time = datetime.now().time()
            else:
                start_time = time(0, 0, 0)

        end_time = time(23, 59, 59) if end_time == '' else end_time

        start_time, end_time = format_time(start_time), format_time(end_time)

        results = con.execute('SELECT stop_id FROM stops_stops_clusters WHERE stop_cluster_id = ?',
                              (stop_id,)).fetchall()
        stop_ids = [result[0] for result in results]

        end_time_statement = f'AND departure_time <= ?' if end_time != '23:59:59' else ''
        query = """SELECT departure_time, route_short_name, trip_headsign, trips.trip_id, stop_sequence
                    FROM stop_times
                             INNER JOIN trips ON stop_times.trip_id = trips.trip_id
                             INNER JOIN routes ON trips.route_id = routes.route_id
                    WHERE stop_times.stop_id in ({stop_id})
                      AND trips.service_id in ({seq})
                      AND pickup_type = 0
                      AND departure_time >= ?
                      AND direction_id = ?
                      {end_time_statement}
                      {route}
                    ORDER BY departure_time, route_short_name, trip_headsign""".format(
            seq=','.join(['?'] * len(service_ids)), stop_id=','.join(['?'] * len(stop_ids)), route=route, end_time_statement=end_time_statement)

        params = (*stop_ids, *service_ids, start_time, self.line_direction)

        if end_time != '23:59:59':
            params += (end_time,)

        if line != '':
            params += (line,)

        cur = con.cursor()
        results = cur.execute(query, params)
        return results.fetchall()

    def format_times_text(self, results, times_history):
        if times_history is None:
            times_history = []
        text = f'{self.title()}'

        full_count = len(results)

        if self.day < date.today():
            text += f'\nNon possiamo mostrare orari di giornate passate. Torna alla giornata odierna o a una futura.'
            return text, None, times_history

        if full_count == 0:
            text += '\nNessun orario trovato per questi filtri.'

        results_to_display = results[:LIMIT]

        choice_buttons = []
        for i, result in enumerate(results_to_display):
            time_raw, line, headsign, trip_id, stop_sequence = result
            time_format = get_time(time_raw).isoformat(timespec="minutes")
            text += f'\n{i + 1}. {time_format} {line} {headsign}'
            callback_data = f'R{trip_id}/{self.day.strftime("%Y%m%d")}/{stop_sequence}/{line}'
            choice_buttons.append(InlineKeyboardButton(f'{i + 1}', callback_data=callback_data))

        keyboard = []
        len_choice_buttons = len(choice_buttons)
        if len_choice_buttons > MAX_CHOICE_BUTTONS_PER_ROW:
            keyboard = split_list(choice_buttons)
        elif len_choice_buttons > 0:
            keyboard.append([button for button in choice_buttons])

        if full_count > LIMIT:
            text += f'\n<i>... e altri {full_count - LIMIT} orari</i>'

        # Time buttons
        times = [result[0] for result in results][LIMIT:]
        len_times = len(times)
        times_buttons = []

        if not times_history:
            times_history = [(self.start_time, self.end_time)]

        if self.direction == 1:  # I am going down
            times_history.append((self.start_time, self.end_time))
        if self.direction == -1:  # I am going up
            times_history.pop()

        if len(times_history) > 1:
            prev_start_time, prev_end_time = times_history[-2]
            times_buttons.append(
                self.inline_button("<<", start_time=prev_start_time, end_time=prev_end_time, direction=-1))
            group_numbers = 2 if len_times > LIMIT else 1
        else:
            group_numbers = 3

        if len_times > 0:
            for time_range in times_groups(times, group_numbers):
                start_time = get_time(time_range[0])
                end_time = get_time(time_range[1])
                time_text = f'{start_time.strftime("%H:%M")}-{end_time.strftime("%H:%M")}'
                times_buttons.append(
                    self.inline_button(time_text, start_time=start_time, end_time=end_time, direction=1))
        keyboard.append(times_buttons)

        # Lines buttons
        if self.line == '':
            lines = list(dict.fromkeys([result[1] for result in results]))

            limit = 4 if 0 < self.offset_lines < len(lines) - 5 else 5
            prev_limit = 5 if self.offset_lines == 5 else 4

            line_buttons = [self.inline_button(line, line=line, direction='') for line in
                            lines[self.offset_lines:self.offset_lines + limit]]
            if self.offset_lines > 0:
                line_buttons.insert(0, self.inline_button('<<', offset_lines=self.offset_lines - prev_limit))
            if self.offset_lines + 5 < len(lines):
                line_buttons.append(self.inline_button('>>', offset_lines=self.offset_lines + limit))
            len_line_buttons = len(line_buttons)
            if len_line_buttons > 1:
                keyboard.append(line_buttons)
        else:
            keyboard.append([self.inline_button('Tutte le linee', line='', direction='')])

        keyboard.append([self.inline_button('cambia direzione', line_direction='switch')])

        reply_markup = InlineKeyboardMarkup(keyboard)
        return text, reply_markup, times_history