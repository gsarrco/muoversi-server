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


class Route:
    def __init__(self, dep_stop_time: StopTime, arr_stop_time: StopTime | None, route_name, headsign, trip_id):
        self.dep_stop_time = dep_stop_time
        self.arr_stop_time = arr_stop_time
        self.route_name = route_name
        self.headsign = headsign
        self.trip_id = trip_id


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
