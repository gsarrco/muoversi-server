import logging

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

    trenitalia = Trenitalia(force_update_stations=force_update_stations)
    trenitalia.save_trains()


if __name__ == '__main__':
    run()
