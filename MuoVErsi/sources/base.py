class Stop:
    def __init__(self, id_, name):
        self.id_ = id_
        self.name = name


class Source:
    def __init__(self, name):
        self.name = name

    def search_stops(self, name=None, lat=None, lon=None) -> list[Stop]:
        raise NotImplementedError


class StopArrivals:
    pass
