from datetime import datetime


class Stop:
    def __init__(self, ref: str, name: str, ids=None):
        if ids is None:
            ids = []
        self.ref = ref
        self.name = name
        self.ids = ids


class StopTime:
    def __init__(self, dep_time: datetime, route_name, headsign, trip_id, stop_sequence, arr_time=None, dep_delay=0,
                 arr_delay=0):
        self.dep_time = dep_time
        self.route_name = route_name
        self.headsign = headsign
        self.trip_id = trip_id
        self.stop_sequence = stop_sequence
        self.arr_time = arr_time
        self.dep_delay = dep_delay
        self.arr_delay = arr_delay


class Source:
    def __init__(self, name, allow_offset_buttons_single_stop):
        self.name = name
        self.allow_offset_buttons_single_stop = allow_offset_buttons_single_stop

    def search_stops(self, name=None, lat=None, lon=None, limit=4) -> list[Stop]:
        raise NotImplementedError

    def get_stop_times(self, line, start_time, dep_stop_ids, service_ids, LIMIT, day, offset_times) -> list[StopTime]:
        raise NotImplementedError

    def get_stop_times_between_stops(self, dep_stop_ids: set, arr_stop_ids: set, service_ids, line, start_time,
                                     offset_times, limit, day) -> list[StopTime]:
        raise NotImplementedError

    def get_service_ids(self, day, service_ids) -> tuple:
        return service_ids

    def get_lines_from_stops(self, service_ids, stop_ids):
        return []

    def get_stop_from_ref(self, ref) -> Stop:
        raise NotImplementedError
