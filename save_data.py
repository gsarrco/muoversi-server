import logging

from sqlalchemy.orm import sessionmaker

from server.GTFS import GTFS
from server.sources import engine
from server.trenitalia import Trenitalia
from server.typesense import connect_to_typesense

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


def run():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--force_update_stations', action='store_true')
    args = parser.parse_args()
    force_update_stations = args.force_update_stations

    session = sessionmaker(bind=engine)()
    typesense = connect_to_typesense()

    sources = [
        GTFS('automobilistico', '🚌', session, typesense),
        GTFS('navigazione', '⛴️', session, typesense),
        Trenitalia(session, typesense, force_update_stations=force_update_stations),
    ]

    for source in sources:
        try:
            source.save_data()
        except KeyboardInterrupt:
            session.rollback()


if __name__ == '__main__':
    run()
