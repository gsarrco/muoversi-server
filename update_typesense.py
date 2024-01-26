from server.sources import sources
from server.typesense.helpers import sync_stations_typesense


def run():
    for source in sources.values():
        sync_stations_typesense(source.typesense, source.name, source.get_source_stations())


if __name__ == '__main__':
    run()
