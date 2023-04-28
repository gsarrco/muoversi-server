import logging
from datetime import datetime, time, date, timedelta

from babel.dates import format_date
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from MuoVErsi.helpers import time_25_to_1, get_active_service_ids, get_lines_from_stops
from MuoVErsi.sources.GTFS import GTFS

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

LIMIT = 12
MAX_CHOICE_BUTTONS_PER_ROW = LIMIT // 2


class StopTimesFilter:
    def __init__(self, dep_stop_ids=None, day=None, line=None, start_time=None, offset_times=0, offset_lines=0,
                 query_data=None, arr_stop_ids=None, dep_cluster_name=None, arr_cluster_name=None, first_time=False):

        if query_data:
            day_raw, line, start_time_raw, offset_times, offset_lines = \
                query_data.split('/')
            day = datetime.strptime(day_raw, '%Y%m%d').date()
            start_time = time.fromisoformat(start_time_raw) if start_time_raw != '' else ''

        self.dep_stop_ids = dep_stop_ids
        self.arr_stop_ids = arr_stop_ids
        self.day = day
        self.line = line
        self.start_time = start_time
        self.offset_times = int(offset_times)
        self.offset_lines = int(offset_lines)
        self.lines = None
        self.dep_cluster_name = dep_cluster_name
        self.arr_cluster_name = arr_cluster_name
        self.first_time = first_time

    def query_data(self, **new_params):
        original_params = self.__dict__
        to_print = {k: new_params[k] if k in new_params else original_params[k] for k in set(original_params)}
        # order dict by key
        to_print = {k: to_print[k] for k in sorted(to_print)}
        to_print['day'] = to_print['day'].strftime('%Y%m%d')
        to_print['start_time'] = to_print['start_time'].isoformat(timespec='minutes') if to_print[
                                                                                             'start_time'] != '' else ''

        result = f'{to_print["day"]}/{to_print["line"]}/' \
                 f'{to_print["start_time"]}/{to_print["offset_times"]}/{to_print["offset_lines"]}'
        logger.info(result)
        return result

    def title(self, _, lang):
        text = '<b>' + (_('departures') % self.dep_cluster_name).upper() + '\n'

        if self.arr_cluster_name:
            text += (_('arrival') % self.arr_cluster_name).upper() + '\n'

        text += format_date(self.day, 'EEEE d MMMM', locale=lang)

        start_time = self.start_time

        if start_time != '':
            text += f' - {self.start_time.strftime("%H:%M")}(-5' + _('min') + ')'

        if self.line != '':
            text += ' - ' + _('line') + ' ' + self.line
        return text + '</b>'

    def inline_button(self, text: str, **new_params):
        return InlineKeyboardButton(text, callback_data=self.query_data(**new_params))

    def get_times(self, db_file: GTFS, service_ids):
        day, dep_stop_ids, line, start_time = self.day, self.dep_stop_ids, self.line, \
            self.start_time

        con = db_file.con

        if service_ids is None:
            service_ids = get_active_service_ids(day, con)

        if self.arr_stop_ids:
            return db_file.get_stop_times_between_stops(set(self.dep_stop_ids), set(self.arr_stop_ids), service_ids,
                                                        line, start_time, self.offset_times, LIMIT, day)

        route = 'AND route_short_name = ?' if line != '' else ''
        departure_time = 'AND departure_time >= ?' if start_time != '' else ''

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
            seq=','.join(['?'] * len(service_ids)), stop_id=','.join(['?'] * len(dep_stop_ids)), route=route,
            departure_time=departure_time)

        params = (*dep_stop_ids, *service_ids)

        if line != '':
            params += (line,)

        if start_time != '':
            start_datetime = datetime.combine(day, start_time)
            minutes_5 = start_datetime - timedelta(minutes=5)
            params += (minutes_5.strftime('%H:%M'),)

        params += (LIMIT, self.offset_times)

        cur = con.cursor()
        results = cur.execute(query, params).fetchall()

        if self.lines is None:
            self.lines = get_lines_from_stops(service_ids, dep_stop_ids, con)

        return results, service_ids

    def format_times_text(self, results, _, lang):
        text = f'{self.title(_, lang)}'

        if self.day < date.today():
            text += '\n' + _('past_date')
            return text, None

        results_len = len(results)

        if results_len == 0:
            text += '\n' + _('no_times')

        for result in results:
            time_raw, line, headsign, trip_id, stop_sequence = result[:5]
            dep_time = time_25_to_1(self.day, time_raw)
            time_format = dep_time.time().isoformat(timespec="minutes")
            if len(result) > 5:
                arr_time = time_25_to_1(self.day, result[5])
                arr_time_format = arr_time.time().isoformat(timespec="minutes")
                time_format += f'->{arr_time_format}'

            if dep_time < datetime.now():
                text += f'\n<del>{time_format} {line} {headsign}</del>'
            else:
                text += f'\n{time_format} {line} {headsign}'

        keyboard = []

        paging_buttons = []

        # prev/next page buttons
        if self.offset_times == 0 and self.start_time != '':
            paging_buttons.append(self.inline_button('<<', start_time=''))
        if results_len > 0:
            if self.offset_times > 0:
                paging_buttons.append(self.inline_button('<', offset_times=self.offset_times - LIMIT))
            if results_len == LIMIT:
                paging_buttons.append(self.inline_button('>', offset_times=self.offset_times + LIMIT))

        keyboard.append(paging_buttons)

        # Lines buttons
        if self.line == '':
            lines = self.lines

            limit = 4 if 0 < self.offset_lines < len(lines) - 5 else 5
            prev_limit = 5 if self.offset_lines == 5 else 4

            line_buttons = [self.inline_button(line, line=line, offset_times=0) for line in
                            lines[self.offset_lines:self.offset_lines + limit]]
            if self.offset_lines > 0:
                line_buttons.insert(0, self.inline_button('<', offset_lines=self.offset_lines - prev_limit))
            if self.offset_lines + 5 < len(lines):
                line_buttons.append(self.inline_button('>', offset_lines=self.offset_lines + limit))
            len_line_buttons = len(line_buttons)
            if len_line_buttons > 1:
                keyboard.append(line_buttons)
        else:
            keyboard.append([self.inline_button(_('all_lines'), line='', offset_times=0)])

        # change day buttons
        now = datetime.now()
        plus_day = self.day + timedelta(days=1)
        plus_day_start_time = now.time() if plus_day == date.today() else ''
        day_buttons = [self.inline_button(_('plus_day'), day=plus_day, start_time=plus_day_start_time, offset_times=0)]
        if self.day > date.today():
            minus_day = self.day - timedelta(days=1)
            minus_day_start_time = now.time() if minus_day == date.today() else ''
            day_buttons.insert(0, self.inline_button(_('minus_day'), day=minus_day, start_time=minus_day_start_time,
                                                     offset_times=0))

        keyboard.append(day_buttons)
        reply_markup = InlineKeyboardMarkup(keyboard)
        return text, reply_markup
