import logging
import os
from datetime import datetime, timedelta, time, date
from sqlite3 import Connection

from babel.dates import format_date
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

LIMIT = 12
MAX_CHOICE_BUTTONS_PER_ROW = LIMIT // 2


class StopData:
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


def get_time(time_string):
    str_time = time_string.split(':')
    str_time = [int(x) for x in str_time]
    hours, minutes, seconds = str_time
    microseconds = 0
    if hours > 23:
        hours = hours - 24
        microseconds = 1

    return time(hours, minutes, seconds, microseconds)


def times_groups(times, n):
    def split_into_groups(people, n):
        k, m = divmod(len(people), n)
        groups = [people[i * k + min(i, m):(i + 1) * k + min(i + 1, m)] for i in range(n)]
        return groups

    result = []
    grouped = split_into_groups(times, n)
    for group in grouped:
        first = group[0]
        last = group[-1]
        result.append((first, last))
    return result


def split_list(input_list):
    midpoint = len(input_list) // 2
    first_half = input_list[:midpoint]
    second_half = input_list[midpoint:]
    return [first_half, second_half]


def format_time(time_obj):
    if time_obj.microsecond == 1:
        return str(time_obj.hour + 24).zfill(2) + time_obj.strftime(':%M:%S')
    else:
        return time_obj.isoformat()


def get_active_service_ids(day: date, con: Connection) -> tuple:
    today_ymd = day.strftime('%Y%m%d')
    weekday = day.strftime('%A').lower()

    cur = con.cursor()
    services = cur.execute(
        f'SELECT service_id FROM calendar WHERE {weekday} = 1 AND start_date <= ? AND end_date >= ?',
        (today_ymd, today_ymd))

    if not services:
        return ()

    service_ids = set([service[0] for service in services.fetchall()])

    service_exceptions = cur.execute('SELECT service_id, exception_type FROM calendar_dates WHERE date = ?',
                                     (today_ymd,))

    for service_exception in service_exceptions.fetchall():
        service_id, exception_type = service_exception
        if exception_type == 1:
            service_ids.add(service_id)
        if exception_type == 2:
            service_ids.remove(service_id)

    service_ids = tuple(service_ids)
    return service_ids


def search_lines(line_name, service_ids, con: Connection):
    cur = con.cursor()
    query = """SELECT trips.trip_id, route_short_name, route_long_name, count(stop_times.id) as times_count
                    FROM stop_times
                        INNER JOIN trips ON stop_times.trip_id = trips.trip_id
                        INNER JOIN routes ON trips.route_id = routes.route_id
                    WHERE route_short_name = ?
                        AND trips.service_id in ({seq})
                    GROUP BY routes.route_id ORDER BY times_count DESC;""".format(
        seq=','.join(['?'] * len(service_ids)))

    cur = con.cursor()
    results = cur.execute(query, (line_name, *service_ids)).fetchall()
    return results


def get_stops_from_trip_id(trip_id, con: Connection, stop_sequence: int = 0):
    cur = con.cursor()
    results = cur.execute('''
        SELECT sc.id, stop_name, departure_time
        FROM stop_times
                 INNER JOIN stops ON stops.stop_id = stop_times.stop_id
                 LEFT JOIN stops_stops_clusters ssc on stops.stop_id = ssc.stop_id
                 LEFT JOIN stops_clusters sc on ssc.stop_cluster_id = sc.id
        WHERE trip_id = ?
          AND stop_sequence >= ?
        ORDER BY stop_sequence
    ''', (trip_id, stop_sequence)).fetchall()
    return results


def find_longest_prefix(str1, str2):
    words1 = str1.split()
    words2 = str2.split()
    prefix = ""
    for i in range(min(len(words1), len(words2))):
        if words1[i] == words2[i]:
            prefix += words1[i] + " "
        else:
            break
    return prefix.strip()


def cluster_strings(stops):
    stops.sort(key=lambda x: x[1])
    longest_prefix = ''
    clusters = {}
    for i1 in range(len(stops)):
        i2 = i1 + 1
        ref_el = stops[i1]
        first_string = ref_el[1]
        second_string = stops[i2][1] if i2 < len(stops) else ''
        first_string, second_string = first_string.strip().upper(), second_string.strip().upper()
        new_cluster = True
        new_longest_prefix = find_longest_prefix(first_string, second_string).rstrip(' "').rstrip()

        if longest_prefix != '':
            # space = " " if len(first_string.split()) > 1 else ""
            if first_string.startswith(longest_prefix) \
                    and len(new_longest_prefix) <= len(longest_prefix):
                new_cluster = False

        if new_cluster:
            longest_prefix = new_longest_prefix

        cluster_name = longest_prefix if longest_prefix != '' and len(longest_prefix) > (
                    len(first_string) / 3) else first_string
        # add_to_cluster(clusters, cluster_name, first_string, stops[i1][2:4])
        clusters.setdefault(cluster_name, {'stops': []})['stops'].append(
            {'stop_id': ref_el[0], 'stop_name': first_string, 'coords': (ref_el[2], ref_el[3]),
             'times_count': ref_el[4]})

    return clusters
