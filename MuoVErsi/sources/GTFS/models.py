class CStop:
    def __init__(self, id_, name, lat, lon, times_count):
        self.id = id_
        self.name = name
        self.lat = lat
        self.lon = lon
        self.times_count = times_count


class CCluster:
    def __init__(self, name: str, stops: list[CStop] = None, lat: str = None, lon: str = None, times_count: int = None):
        self.name = name
        if stops is None:
            stops = []
        self.stops = stops
        self.lat = lat
        self.lon = lon
        self.times_count = times_count
