import logging
from datetime import time, date
from sqlite3 import Connection

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

LIMIT = 12
MAX_CHOICE_BUTTONS_PER_ROW = LIMIT // 2


def time_25_to_1(time_string):
    str_time = time_string.split(':')
    str_time = [int(x) for x in str_time]
    hours, minutes, seconds = str_time
    if hours > 23:
        hours = hours - 24

    return time(hours, minutes, seconds)


def times_groups(times, n):
    def split_into_groups(people, n):
        k, m = divmod(len(people), n)
        groups = [people[i * k + min(i, m):(i + 1) * k + min(i + 1, m)] for i in range(n)]
        return groups

    result = []
    grouped = split_into_groups(times, n)
    for group in grouped:
        first = group[0]
        last = group[-1]
        result.append((first, last))
    return result


def split_list(input_list):
    midpoint = len(input_list) // 2
    first_half = input_list[:midpoint]
    second_half = input_list[midpoint:]
    return [first_half, second_half]


def get_active_service_ids(day: date, con: Connection) -> tuple:
    today_ymd = day.strftime('%Y%m%d')
    weekday = day.strftime('%A').lower()

    cur = con.cursor()
    services = cur.execute(
        f'SELECT service_id FROM calendar WHERE {weekday} = 1 AND start_date <= ? AND end_date >= ?',
        (today_ymd, today_ymd))

    if not services:
        return ()

    service_ids = set([service[0] for service in services.fetchall()])

    service_exceptions = cur.execute('SELECT service_id, exception_type FROM calendar_dates WHERE date = ?',
                                     (today_ymd,))

    for service_exception in service_exceptions.fetchall():
        service_id, exception_type = service_exception
        if exception_type == 1:
            service_ids.add(service_id)
        if exception_type == 2:
            service_ids.remove(service_id)

    service_ids = tuple(service_ids)
    return service_ids


def search_lines(line_name, service_ids, con: Connection):
    cur = con.cursor()
    query = """SELECT trips.trip_id, route_short_name, route_long_name, count(stop_times.id) as times_count
                    FROM stop_times
                        INNER JOIN trips ON stop_times.trip_id = trips.trip_id
                        INNER JOIN routes ON trips.route_id = routes.route_id
                    WHERE route_short_name = ?
                        AND trips.service_id in ({seq})
                    GROUP BY routes.route_id ORDER BY times_count DESC;""".format(
        seq=','.join(['?'] * len(service_ids)))

    cur = con.cursor()
    results = cur.execute(query, (line_name, *service_ids)).fetchall()
    return results


def get_stops_from_trip_id(trip_id, con: Connection, stop_sequence: int = 0):
    cur = con.cursor()
    results = cur.execute('''
        SELECT sc.id, stop_name, departure_time
        FROM stop_times
                 INNER JOIN stops ON stops.stop_id = stop_times.stop_id
                 LEFT JOIN stops_stops_clusters ssc on stops.stop_id = ssc.stop_id
                 LEFT JOIN stops_clusters sc on ssc.stop_cluster_id = sc.id
        WHERE trip_id = ?
          AND stop_sequence >= ?
        ORDER BY stop_sequence
    ''', (trip_id, stop_sequence)).fetchall()
    return results


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


def get_lines_from_stops(service_ids, stop_ids, con: Connection):
    cur = con.cursor()
    query = """
                SELECT route_short_name
                FROM stop_times
                         INNER JOIN trips ON stop_times.trip_id = trips.trip_id
                         INNER JOIN routes ON trips.route_id = routes.route_id
                WHERE stop_times.stop_id in ({stop_id})
                  AND trips.service_id in ({seq})
                  AND pickup_type = 0
                GROUP BY route_short_name ORDER BY count(*) DESC;
            """.format(seq=','.join(['?'] * len(service_ids)), stop_id=','.join(['?'] * len(stop_ids)))

    params = (*stop_ids, *service_ids)

    return [line[0] for line in cur.execute(query, params).fetchall()]
