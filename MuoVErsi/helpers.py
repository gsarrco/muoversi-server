import logging
from datetime import time, date, datetime, timedelta

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

LIMIT = 12
MAX_CHOICE_BUTTONS_PER_ROW = LIMIT // 2


def time_25_to_1(day: date, time_string) -> datetime:
    str_time = time_string.split(':')
    str_time = [int(x) for x in str_time]
    hours, minutes, seconds = str_time
    if hours > 23:
        hours = hours - 24
        day = day + timedelta(days=1)

    return datetime.combine(day, time(hours, minutes, seconds))


