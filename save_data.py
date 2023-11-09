import logging
from datetime import date, timedelta

from sqlalchemy import inspect

from server.GTFS import GTFS
from server.base.models import StopTime
from server.sources import engine, session
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

    typesense = connect_to_typesense()

    sources = [
        GTFS('automobilistico', '🚌', session, typesense),
        GTFS('navigazione', '⛴️', session, typesense),
        Trenitalia(session, typesense, force_update_stations=force_update_stations),
    ]

    session.commit()

    today = date.today()

    for i in range(3):
        day: date = today + timedelta(days=i)
        partition = StopTime.create_partition(day)
        if not inspect(engine).has_table(partition.__table__.name):
            partition.__table__.create(bind=engine)

    while True:
        i = -2
        day = today + timedelta(days=i)
        try:
            StopTime.detach_partition(day)
        except Exception:
            break

    for source in sources:
        try:
            source.save_data()
        except KeyboardInterrupt:
            session.rollback()


if __name__ == '__main__':
    run()
