from datetime import datetime


class Stop:
    def __init__(self, ref: str, name: str, ids=None):
        if ids is None:
            ids = []
        self.ref = ref
        self.name = name
        self.ids = ids


class StopTime:
    def __init__(self, dt: datetime, stop_sequence, delay: int, platform):
        self.dt = dt
        self.stop_sequence = stop_sequence
        self.delay = delay
        self.platform = platform


class Liner:
    def format(self):
        raise NotImplementedError


class Route(Liner):
    def __init__(self, dep_stop_time: StopTime, arr_stop_time: StopTime | None, route_name, headsign, trip_id):
        self.dep_stop_time = dep_stop_time
        self.arr_stop_time = arr_stop_time
        self.route_name = route_name
        self.headsign = headsign
        self.trip_id = trip_id

    def format(self, left_time_bold=True, right_time_bold=True):
        line, headsign, trip_id, stop_sequence = self.route_name, self.headsign, \
            self.trip_id, self.dep_stop_time.stop_sequence

        time_format = ""

        if left_time_bold:
            time_format += "<b>"

        time_format += self.dep_stop_time.dt.strftime('%H:%M')

        if self.dep_stop_time.delay > 0:
            time_format += f'+{self.dep_stop_time.delay}m'

        if left_time_bold:
            time_format += "</b>"

        if self.arr_stop_time:
            arr_time = self.arr_stop_time.dt.strftime('%H:%M')

            time_format += "->"

            if right_time_bold:
                time_format += "<b>"

            time_format += arr_time

            if self.arr_stop_time.delay > 0:
                time_format += f'+{self.arr_stop_time.delay}m'

            if right_time_bold:
                time_format += "</b>"

        if self.dep_stop_time.platform:
            line = f'{time_format} {headsign}\n⎿ {line} BIN. {self.dep_stop_time.platform}'
        else:
            line = f'{time_format} {line} {headsign}'

        if self.dep_stop_time.dt < datetime.now():
            line = f'<del>{line}</del>'

        return f'\n{line}'


class Direction(Liner):
    def __init__(self, routes: list[Route]):
        self.routes = routes

    def format(self):
        text = ""
        for i, route in enumerate(self.routes):
            text += route.format(left_time_bold=i == 0, right_time_bold=i == len(self.routes) - 1)
        return text


class Source:
    def __init__(self, name, allow_offset_buttons_single_stop):
        self.name = name
        self.allow_offset_buttons_single_stop = allow_offset_buttons_single_stop

    def search_stops(self, name=None, lat=None, lon=None, limit=4) -> list[Stop]:
        raise NotImplementedError

    def get_stop_times(self, line, start_time, dep_stop_ids, service_ids, LIMIT, day, offset_times) -> list[Route]:
        raise NotImplementedError

    def get_stop_times_between_stops(self, dep_stop_ids: set, arr_stop_ids: set, service_ids, line, start_time,
                                     offset_times, limit, day) -> list[Route]:
        raise NotImplementedError

    def get_service_ids(self, day, service_ids) -> tuple:
        return service_ids

    def get_lines_from_stops(self, service_ids, stop_ids):
        return []

    def get_stop_from_ref(self, ref) -> Stop:
        raise NotImplementedError
