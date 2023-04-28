class Source:
    def __init__(self, name):
        self.name = name

    def search_stops(self, name=None, lat=None, lon=None):
        raise NotImplementedError
