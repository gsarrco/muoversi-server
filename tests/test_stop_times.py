from datetime import time, date, datetime, timedelta

import pytest

from MuoVErsi.sources.GTFS import GTFS


@pytest.fixture
def db_file():
    return GTFS('navigazione', 541, 'tests/data')


def test_night_stop_times(db_file):
    start_time = time(0, 33, 14, 379232)
    dep_stop_ids = [5031]
    service_ids = ('320815_000',)
    day = date(2023, 2, 11)
    stop_times = db_file.get_stop_times('', start_time, dep_stop_ids, service_ids, day, 0, 'P.LE ROMA')

    day_after = day + timedelta(days=1)
    check_start_dt = datetime.combine(day_after, time(0, 0))
    check_end_dt = datetime.combine(day_after, time(4, 0))
    assert any(stop_time for stop_time in stop_times if
               check_start_dt < stop_time.dep_time < check_end_dt), 'no stop_times with dep_time before 4 am'
