from server.sources import typesense, session
from server.typesense.helpers import sync_stations_typesense


if __name__ == '__main__':
    sync_stations_typesense(typesense, session)
