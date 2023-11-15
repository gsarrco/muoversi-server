import logging
from datetime import date, timedelta

from sqlalchemy import inspect, text

from server.sources import engine, session

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


def run():
    session.commit()

    today = date.today()

    def part_name(day: date):
        return f'stop_times_{day.strftime("%Y%m%d")}'

    for i in range(3):
        day: date = today + timedelta(days=i)
        day_after: date = day + timedelta(days=1)
        partition_name = part_name(day)
        if not inspect(engine).has_table(partition_name):
            session.execute(text(f"CREATE TABLE {partition_name} PARTITION OF stop_times FOR VALUES FROM ('{day}') TO ('{day_after}')"))
            session.commit()
    # start from the day before yesterday for detaching partitions
    i = 2
    while True:
        day = today - timedelta(days=i)
        try:
            session.execute(text(f'ALTER TABLE stop_times DETACH PARTITION {part_name(day)}'))
            session.commit()
        except:
            session.rollback()
            break
        i += 1


if __name__ == '__main__':
    run()
