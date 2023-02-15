import pytest

from MuoVErsi.db import DBFile, get_clusters_of_stops
from MuoVErsi.helpers import search_stops


@pytest.fixture
def automobilistico_db_file():
    return DBFile('automobilistico', 640)

@pytest.fixture
def navigazione_db_file():
    return DBFile('navigazione', 541)

@pytest.fixture
def db_files(automobilistico_db_file, navigazione_db_file):
    return [automobilistico_db_file, navigazione_db_file]

@pytest.fixture
def stops_and_stops_clusters(db_files):
    result = []
    for db_file in db_files:
        stops = db_file.get_all_stops()
        stops_clusters = get_clusters_of_stops(stops)
        result.append((stops, stops_clusters))
    return result


def test_stops_clusters_tables_created(db_files):
    for db_file in db_files:
        cur = db_file.con.cursor()
        cur.execute('DROP TABLE IF EXISTS stops_clusters')
        cur.execute('DROP TABLE IF EXISTS stops_stops_clusters')
        db_file.upload_stops_clusters_to_db()
        cur.execute('SELECT name FROM sqlite_master WHERE type="table" AND name="stops_clusters"')
        assert cur.fetchone(), 'stops_clusters table not created'
        cur.execute('SELECT name FROM sqlite_master WHERE type="table" AND name="stops_stops_clusters"')
        assert cur.fetchone(), 'stops_stops_clusters table not created'


def test_search_stops_by_name(automobilistico_db_file):
    con = automobilistico_db_file.con
    con.set_trace_callback(print)
    results = search_stops(con, "mestre centro")

    if isinstance(results, list):
        is_valid = all(isinstance(elem, tuple) and len(elem) == 2 for elem in results)
    else:
        is_valid = False

    assert is_valid, 'search_stops_by_name does not return a list of tuples of size 2'


def test_clusters_stops_structure(stops_and_stops_clusters):
    for _, stops_clusters in stops_and_stops_clusters:
        assert all('stops' in cluster for cluster in stops_clusters.values()), 'not all clusters have stops'
        assert all('coords' in cluster for cluster in stops_clusters.values()), 'not all clusters have coords'
        assert all('times_count' in cluster for cluster in stops_clusters.values()), 'not all clusters have times_count'


def test_cluster_times_count_equals_sum_of_stops_times_count(stops_and_stops_clusters):
    for stops, stops_clusters in stops_and_stops_clusters:
        for cluster in stops_clusters.values():
            assert cluster['times_count'] == sum(stop['times_count'] for stop in cluster[
                'stops']), 'cluster times_count is not equal to sum of stops times_count'


def test_all_stops_are_in_clusters(stops_and_stops_clusters):
    for stops, stops_clusters in stops_and_stops_clusters:
        flat_result = sorted(
            [stop['stop_name'].strip().upper() + '_' + stop['stop_id'] for stops_cluster in stops_clusters.values() for
             stop in stops_cluster['stops']])

        actual_strings = sorted([item[1].strip().upper() + '_' + item[0] for item in stops])

        assert actual_strings == flat_result, 'not all stops are in the clusters'
