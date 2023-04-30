class Stop:
    def __init__(self, id_, name):
        self.id_ = id_
        self.name = name


class StopTime:
    def __init__(self, departure_time, route_name, headsign, trip_id, stop_sequence, arr_time=None):
        self.departure_time = departure_time
        self.route_name = route_name
        self.headsign = headsign
        self.trip_id = trip_id
        self.stop_sequence = stop_sequence
        self.arr_time = arr_time


class Source:
    def __init__(self, name):
        self.name = name

    def search_stops(self, name=None, lat=None, lon=None) -> list[Stop]:
        raise NotImplementedError

    def get_stop_times(self, line, start_time, dep_stop_ids, service_ids, LIMIT, day, offset_times) -> list[StopTime]:
        raise NotImplementedError

    def get_service_ids(self, day, service_ids) -> tuple:
        return service_ids

    def get_lines_from_stops(self, service_ids, stop_ids):
        raise []
