from datetime import time, date, datetime

import pytest

from MuoVErsi.sources.GTFS import GTFS


@pytest.fixture
def db_file():
    return GTFS('navigazione', 541, 'tests/data')


def test_night_stop_times(db_file):
    start_time = time(0, 33, 14, 379232)
    dep_stop_ids = [5031]
    day = date(2023, 2, 11)
    stop_times = db_file.get_stop_times('', start_time, dep_stop_ids, day, 0, 'P.LE ROMA')

    check_start_dt = datetime.combine(day, time(0, 0))
    check_end_dt = datetime.combine(day, time(4, 0))
    assert any(stop_time for stop_time in stop_times if
               check_start_dt < stop_time.dep_time < check_end_dt), 'no stop_times with dep_time before 4 am'


def test_night_stop_times_new_service(db_file):
    start_time = time(0, 33, 14, 379232)
    dep_stop_ids = [5031]
    day = date(2023, 2, 8)
    stop_times = db_file.get_stop_times('', start_time, dep_stop_ids, day, 0, 'P.LE ROMA')

    check_start_dt = datetime.combine(day, time(0, 0))
    check_end_dt = datetime.combine(day, time(6, 0))
    assert not any(stop_time for stop_time in stop_times if
                   check_start_dt < stop_time.dep_time < check_end_dt), 'stop_times with dep_time before 6 am'
    assert any(stop_time for stop_time in stop_times if
               stop_time.dep_time > check_end_dt), 'no stop_times with dep_time after 6 am'
