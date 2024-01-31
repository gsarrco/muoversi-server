from datetime import datetime

from server.base.models import StopTime


class Liner:
    def format(self, number, _, source_name):
        raise NotImplementedError


class NamedStopTime(Liner):
    def __init__(self, stop_time: StopTime, station_name: str):
        self.stop_time = stop_time
        self.station_name = station_name

    def format(self, number, _, source_name, left_time_bold=True, right_time_bold=True):
        # First line of text
        time_format = ""

        if left_time_bold:
            time_format += "<b>"

        time_format += self.stop_time.sched_dep_dt.strftime('%H:%M')

        if left_time_bold:
            time_format += "</b>"

        headsign = self.stop_time.dest_text[:21]
        route_name = f'{self.stop_time.route_name} ' if self.stop_time.route_name else ''
        line = f'{time_format} {route_name}{headsign}'

        # Second line of text
        trip_id = f'/{self.stop_time.number} ' if self.stop_time.number else ''
        platform = self.stop_time.platform if self.stop_time.platform else '/'
        platform_text = _(f'{source_name}_platform')
        line += f'\n⎿ <i>{trip_id}{platform_text} {platform}</i>'

        # Modifications for all lines of text
        if self.stop_time.sched_dep_dt < datetime.now(tz=self.stop_time.sched_dep_dt.tzinfo):
            line = f'<del>{line}</del>'

        if number:
            return f'\n{number}. {line}'
        else:
            return f'\n⎿ {line}'


class Route(Liner):
    def __init__(self, dep_named_stop_time: NamedStopTime,
                 arr_named_stop_time: NamedStopTime | None = None):
        self.dep_stop_time = dep_named_stop_time.stop_time
        self.dep_station_name = dep_named_stop_time.station_name
        self.arr_stop_time = arr_named_stop_time.stop_time if arr_named_stop_time else None
        self.arr_station_name = arr_named_stop_time.station_name if arr_named_stop_time else None

    def format(self, number, _, source_name, left_time_bold=True, right_time_bold=True):
        # First line of text
        time_format = ""

        if left_time_bold:
            time_format += "<b>"

        time_format += self.dep_stop_time.sched_dep_dt.strftime('%H:%M')

        if left_time_bold:
            time_format += "</b>"

        if self.arr_stop_time:
            arr_time = self.arr_stop_time.sched_arr_dt.strftime('%H:%M')

            time_format += "->"

            if right_time_bold:
                time_format += "<b>"

            time_format += arr_time

            if right_time_bold:
                time_format += "</b>"

        headsign = self.dep_stop_time.dest_text[:14]
        route_name = f'{self.dep_stop_time.route_name} ' if self.dep_stop_time.route_name else ''
        line = f'{time_format} {route_name}{headsign}'

        # Second line of text
        platform_text = _(f'{source_name}_platform')
        dep_platform = self.dep_stop_time.platform if self.dep_stop_time.platform else '/'
        arr_platform = self.arr_stop_time.platform if self.arr_stop_time.platform else '/'
        line += f'\n⎿ <i>/{self.dep_stop_time.number} {platform_text} {dep_platform} -> {arr_platform}</i>'

        # Modifications for all lines of text
        if self.dep_stop_time.sched_dep_dt < datetime.now(tz=self.dep_stop_time.sched_dep_dt.tzinfo):
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

            if route.arr_station_name and i != len(self.routes) - 1:
                next_route = self.routes[i + 1]
                duration_in_minutes = (
                                              next_route.dep_stop_time.sched_dep_dt - route.arr_stop_time.sched_dep_dt).seconds // 60
                text += f'\n⎿ <i>cambio a {route.arr_station_name} ({duration_in_minutes}min)</i>'

        return text
