import logging

import yaml

from MuoVErsi.sources.trenitalia import Trenitalia

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


def run():
    with open('config.yaml' , 'r') as config_file:
        try:
            config = yaml.safe_load(config_file)
            logger.info(config)
        except yaml.YAMLError as err:
            logger.error(err)

    DEV = config.get('DEV', False)

    PGUSER = config.get('PGUSER', None)
    PGPASSWORD = config.get('PGPASSWORD', None)
    PGHOST = config.get('PGHOST', None)
    PGPORT = config.get('PGPORT', 5432)
    PGDATABASE = config.get('PGDATABASE', None)

    trenitalia = Trenitalia(PGUSER, PGPASSWORD, PGHOST, PGPORT, PGDATABASE, dev=DEV)
    trenitalia.save_trains()


if __name__ == '__main__':
    run()
