from datetime import datetime

from telegram.ext import ContextTypes


class Stop:
    def __init__(self, ref: str, name: str, ids=None):
        if ids is None:
            ids = []
        self.ref = ref
        self.name = name
        self.ids = ids


class Liner:
    def format(self, number, _, source_name):
        raise NotImplementedError


class StopTime(Liner):
    def __init__(self, dep_time: datetime | None, arr_time: datetime | None, stop_sequence, delay: int, platform,
                 headsign, trip_id,
                 route_name, stop_name: str = None):
        self.dep_time = dep_time
        self.arr_time = arr_time
        self.stop_sequence = stop_sequence
        self.delay = delay
        self.platform = platform
        self.headsign = headsign
        self.trip_id = trip_id
        self.route_name = route_name
        self.stop_name = stop_name

    def format(self, number, _, source_name, left_time_bold=True, right_time_bold=True):
        headsign, trip_id, stop_sequence = self.headsign, self.trip_id, self.stop_sequence

        # First line of text
        time_format = ""

        if left_time_bold:
            time_format += "<b>"

        time_format += self.dep_time.strftime('%H:%M')

        if self.delay > 0:
            time_format += f'+{self.delay}m'

        if left_time_bold:
            time_format += "</b>"

        headsign = headsign[:21]
        route_name = f'{self.route_name} ' if self.route_name else ''
        line = f'{time_format} {route_name}{headsign}'

        # Second line of text
        trip_id = self.trip_id if source_name == 'treni' else None
        platform = self.platform

        second_line_elements = [trip_id, platform]
        if any(second_line_elements):
            trip_id = f'{trip_id} ' if trip_id else ''
            platform = platform if platform else '/'
            platform_text = _(f'{source_name}_platform')
            line += f'\n⎿ <i>{trip_id}{platform_text} {platform}</i>'

        # Modifications for all lines of text
        if self.dep_time < datetime.now():
            line = f'<del>{line}</del>'

        if number:
            return f'\n{number}. {line}'
        else:
            return f'\n⎿ {line}'


class Route(Liner):
    def __init__(self, dep_stop_time: StopTime, arr_stop_time: StopTime | None):
        self.dep_stop_time = dep_stop_time
        self.arr_stop_time = arr_stop_time

    def format(self, number, _, source_name, left_time_bold=True, right_time_bold=True):
        line, headsign, trip_id, stop_sequence = self.dep_stop_time.route_name, self.dep_stop_time.headsign, \
            self.dep_stop_time.trip_id, self.dep_stop_time.stop_sequence

        # First line of text
        time_format = ""

        if left_time_bold:
            time_format += "<b>"

        time_format += self.dep_stop_time.dep_time.strftime('%H:%M')

        if self.dep_stop_time.delay > 0:
            time_format += f'+{self.dep_stop_time.delay}m'

        if left_time_bold:
            time_format += "</b>"

        if self.arr_stop_time:
            arr_time = self.arr_stop_time.arr_time.strftime('%H:%M')

            time_format += "->"

            if right_time_bold:
                time_format += "<b>"

            time_format += arr_time

            if self.arr_stop_time.delay > 0:
                time_format += f'+{self.arr_stop_time.delay}m'

            if right_time_bold:
                time_format += "</b>"

        headsign = headsign[:14]
        route_name = f'{self.dep_stop_time.route_name} ' if self.dep_stop_time.route_name else ''
        line = f'{time_format} {route_name}{headsign}'

        # Second line of text
        dep_platform = self.dep_stop_time.platform
        arr_platform = self.arr_stop_time.platform
        trip_id = f'{self.dep_stop_time.trip_id} ' if source_name == 'treni' else None
        second_line_elements = [trip_id, dep_platform, arr_platform]
        if any(second_line_elements):
            platform_text = _(f'{source_name}_platform')
            dep_platform = dep_platform if dep_platform else '/'
            arr_platform = arr_platform if arr_platform else '/'
            trip_id = trip_id if trip_id else ''
            line += f'\n⎿ <i>{trip_id}{platform_text} {dep_platform} -> {arr_platform}</i>'

        # Modifications for all lines of text
        if self.dep_stop_time.dep_time < datetime.now():
            line = f'<del>{line}</del>'

        if number:
            return f'\n{number}. {line}'
        else:
            return f'\n⎿ {line}'


class Direction(Liner):
    def __init__(self, routes: list[Route]):
        self.routes = routes

    def format(self, number, _, source_name):
        text = ""
        for i, route in enumerate(self.routes):
            number = number if i == 0 else None
            text += route.format(number, _, source_name, left_time_bold=i == 0,
                                 right_time_bold=i == len(self.routes) - 1)

            if route.arr_stop_time.stop_name and i != len(self.routes) - 1:
                next_route = self.routes[i + 1]
                print(route.arr_stop_time.dep_time, next_route.dep_stop_time.dep_time)
                duration_in_minutes = (next_route.dep_stop_time.dep_time - route.arr_stop_time.dep_time).seconds // 60
                text += f'\n⎿ <i>cambio a {route.arr_stop_time.stop_name} ({duration_in_minutes}min)</i>'

        return text


class Source:
    LIMIT = 7

    def __init__(self, name):
        self.name = name

    def search_stops(self, name=None, lat=None, lon=None, limit=4) -> list[Stop]:
        raise NotImplementedError

    def get_stop_times(self, line, start_time, dep_stop_ids, day,
                       offset_times, dep_stop_name, context: ContextTypes.DEFAULT_TYPE | None = None) -> list[
        StopTime]:
        raise NotImplementedError

    def get_stop_times_between_stops(self, dep_stop_ids: set,
                                     arr_stop_ids: set, line, start_time,
                                     offset_times, day, dep_stop_name, arr_stop_name,
                                     context: ContextTypes.DEFAULT_TYPE | None = None) -> list[Direction]:
        raise NotImplementedError

    def get_lines_from_stops(self, day, stop_ids, context: ContextTypes.DEFAULT_TYPE | None = None) -> list[str]:
        return []

    def get_stop_from_ref(self, ref) -> Stop:
        raise NotImplementedError

    def search_lines(self, name, context: ContextTypes.DEFAULT_TYPE | None = None):
        raise NotImplementedError
