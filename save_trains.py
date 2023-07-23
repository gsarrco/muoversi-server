import logging

from sqlalchemy.orm import sessionmaker

from MuoVErsi.handlers import engine
from MuoVErsi.sources.trenitalia import Trenitalia

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
    trenitalia = Trenitalia(session, force_update_stations=force_update_stations)
    trenitalia.save_trains()


if __name__ == '__main__':
    run()
