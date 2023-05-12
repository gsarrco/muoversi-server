import logging
from datetime import datetime, time, date, timedelta

from babel.dates import format_date
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from MuoVErsi.helpers import time_25_to_1
from MuoVErsi.sources.base import StopTime, Source

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

LIMIT = 10
MAX_CHOICE_BUTTONS_PER_ROW = LIMIT // 2


class StopTimesFilter:
    def __init__(self, source: Source, dep_stop_ids=None, day=None, line=None, start_time=None, offset_times=0, offset_lines=0,
                 query_data=None, arr_stop_ids=None, dep_cluster_name=None, arr_cluster_name=None, first_time=False):

        if query_data:
            day_raw, line, start_time_raw, offset_times, offset_lines = \
                query_data.split('/')
            day = datetime.strptime(day_raw, '%Y%m%d').date()
            start_time = time.fromisoformat(start_time_raw) if start_time_raw != '' else ''

        self.source = source
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

    def get_times(self, db_file: Source, service_ids) -> tuple[list[StopTime], tuple]:
        day, dep_stop_ids, line, start_time = self.day, self.dep_stop_ids, self.line, \
            self.start_time

        service_ids = db_file.get_service_ids(day, service_ids)

        if self.arr_stop_ids:
            results = db_file.get_stop_times_between_stops(set(self.dep_stop_ids), set(self.arr_stop_ids), service_ids,
                                                        line, start_time, self.offset_times, LIMIT, day)
            return results, service_ids

        results = db_file.get_stop_times(line, start_time, dep_stop_ids, service_ids, LIMIT, day, self.offset_times)

        if self.lines is None:
            self.lines = db_file.get_lines_from_stops(service_ids, dep_stop_ids)

        return results, service_ids

    def format_times_text(self, results: list[StopTime], _, lang):
        text = f'{self.title(_, lang)}'

        if self.day < date.today():
            text += '\n' + _('past_date')
            return text, None

        results_len = len(results)

        if results_len == 0:
            text += '\n' + _('no_times')

        for result in results:
            line, headsign, trip_id, stop_sequence = result.route_name, result.headsign, \
                                                                  result.trip_id, result.stop_sequence
            time_raw = result.dep_time.strftime('%H:%M:%S')
            dep_time = time_25_to_1(self.day, time_raw)
            time_format = dep_time.time().isoformat(timespec="minutes")

            if result.dep_delay > 0:
                time_format += f'+{result.dep_delay}m'

            if result.arr_time:
                arr_time = time_25_to_1(self.day, result.arr_time.strftime('%H:%M:%S'))
                arr_time_format = arr_time.time().isoformat(timespec="minutes")
                time_format += f'->{arr_time_format}'

                if result.arr_delay > 0:
                    time_format += f'+{result.arr_delay}m'

            if result.platform:
                line = f'<b>{time_format}</b> {headsign}\n⎿ {line} BIN. {result.platform}'
            else:
                line = f'<b>{time_format}</b> {line} {headsign}'

            if dep_time < datetime.now():
                line = f'<del>{line}</del>'

            text += f'\n{line}'

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

        if self.source.allow_offset_buttons_single_stop:
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
