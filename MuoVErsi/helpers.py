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


def find_longest_prefix(str1, str2):
    words1 = str1.split()
    words2 = str2.split()
    prefix = ""
    for i in range(min(len(words1), len(words2))):
        if words1[i] == words2[i]:
            prefix += words1[i] + " "
        else:
            break
    return prefix.strip()


def cluster_strings(stops):
    stops = [(stop[0], stop[1].upper(), stop[2], stop[3], stop[4]) for stop in stops]
    stops.sort(key=lambda x: x[1])
    longest_prefix = ''
    clusters = {}
    for i1 in range(len(stops)):
        i2 = i1 + 1
        ref_el = stops[i1]
        first_string = ref_el[1]
        second_string = stops[i2][1] if i2 < len(stops) else ''
        first_string, second_string = first_string.strip().upper(), second_string.strip().upper()
        new_cluster = True
        new_longest_prefix = find_longest_prefix(first_string, second_string).rstrip(' "').rstrip()

        if longest_prefix != '':
            # space = " " if len(first_string.split()) > 1 else ""
            if first_string.startswith(longest_prefix) \
                    and len(new_longest_prefix) <= len(longest_prefix):
                new_cluster = False

        if new_cluster:
            longest_prefix = new_longest_prefix

        cluster_name = longest_prefix if longest_prefix != '' and len(longest_prefix) > (
                    len(first_string) / 3) else first_string
        # add_to_cluster(clusters, cluster_name, first_string, stops[i1][2:4])
        clusters.setdefault(cluster_name, {'stops': []})['stops'].append(
            {'stop_id': ref_el[0], 'stop_name': first_string, 'coords': (ref_el[2], ref_el[3]),
             'times_count': ref_el[4]})

    return clusters
