from datetime import datetime


class Stop:
    def __init__(self, ref: str, name: str, ids=None):
        if ids is None:
            ids = []
        self.ref = ref
        self.name = name
        self.ids = ids


class Liner:
    def format(self, number):
        raise NotImplementedError

class StopTime(Liner):
    def __init__(self, dep_time: datetime | None, arr_time: datetime | None, stop_sequence, delay: int, platform, headsign, trip_id,
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

    def format(self, number, left_time_bold=True, right_time_bold=True):
        line, headsign, trip_id, stop_sequence = self.route_name, self.headsign, \
            self.trip_id, self.stop_sequence

        time_format = ""

        if left_time_bold:
            time_format += "<b>"

        time_format += self.dep_time.strftime('%H:%M')

        if self.delay > 0:
            time_format += f'+{self.delay}m'

        if left_time_bold:
            time_format += "</b>"

        if self.platform:
            line = f'{time_format} {headsign}\n⎿ <i>{line} BIN. {self.platform}</i>'
        else:
            line = f'{time_format} {line} {headsign}'

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

    def format(self, number, left_time_bold=True, right_time_bold=True):
        line, headsign, trip_id, stop_sequence = self.dep_stop_time.route_name, self.dep_stop_time.headsign, \
            self.dep_stop_time.trip_id, self.dep_stop_time.stop_sequence

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

        if self.dep_stop_time.platform:
            line = f'{time_format} {headsign}\n⎿ <i>{line} BIN. {self.dep_stop_time.platform}'

            if self.arr_stop_time.platform:
                line += f' -> {self.arr_stop_time.platform}'

            line += '</i>'
        else:
            line = f'{time_format} {line} {headsign}'

        if self.dep_stop_time.dep_time < datetime.now():
            line = f'<del>{line}</del>'

        if number:
            return f'\n{number}. {line}'
        else:
            return f'\n⎿ {line}'


class Direction(Liner):
    def __init__(self, routes: list[Route]):
        self.routes = routes

    def format(self, number):
        text = ""
        for i, route in enumerate(self.routes):
            number = number if i == 0 else None
            text += route.format(number, left_time_bold=i == 0, right_time_bold=i == len(self.routes) - 1)

            if route.arr_stop_time.stop_name and i != len(self.routes) - 1:
                next_route = self.routes[i + 1]
                print(route.arr_stop_time.dep_time, next_route.dep_stop_time.dep_time)
                duration_in_minutes = (next_route.dep_stop_time.dep_time - route.arr_stop_time.dep_time).seconds // 60
                text += f'\n⎿ <i>cambio a {route.arr_stop_time.stop_name} ({duration_in_minutes}min)</i>'

        return text


class Source:
    LIMIT = 10

    def __init__(self, name):
        self.name = name

    def search_stops(self, name=None, lat=None, lon=None, limit=4) -> list[Stop]:
        raise NotImplementedError

    def get_stop_times(self, line, start_time, dep_stop_ids, service_ids, day, offset_times) -> list[StopTime]:
        raise NotImplementedError

    def get_stop_times_between_stops(self, dep_stop_ids: set, arr_stop_ids: set, service_ids, line, start_time,
                                     offset_times, day) -> list[Direction]:
        raise NotImplementedError

    def get_service_ids(self, day, service_ids) -> tuple:
        return service_ids

    def get_lines_from_stops(self, service_ids, stop_ids):
        return []

    def get_stop_from_ref(self, ref) -> Stop:
        raise NotImplementedError
