import logging
from datetime import date, timedelta

from sqlalchemy import inspect, text

from server.base.models import StopTime
from server.sources import engine, session, sources

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


def run():
    session.commit()

    today = date.today()

    for i in range(3):
        day: date = today + timedelta(days=i)
        partition = StopTime.create_partition(day)
        if not inspect(engine).has_table(partition.__table__.name):
            partition.__table__.create(bind=engine)

    # start from the day before yesterday for detaching partitions
    i = 2
    while True:
        day = today - timedelta(days=i)
        try:
            session.execute(text(f'ALTER TABLE stop_times DETACH PARTITION stop_times_{day.strftime("%Y%m%d")}'))
            session.commit()
        except:
            session.rollback()
            break
        i += 1

    for source in sources.values():
        try:
            source.save_data()
        except KeyboardInterrupt:
            session.rollback()


if __name__ == '__main__':
    run()
