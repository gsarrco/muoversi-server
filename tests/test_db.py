import pytest

from MuoVErsi.sources.GTFS import GTFS, get_clusters_of_stops, CCluster, CStop


@pytest.fixture
def db_file():
    return GTFS('navigazione', 541, 'tests/data')


@pytest.fixture
def stops_and_stops_clusters(db_file) -> tuple[list[CStop], list[CCluster]]:
    stops = db_file.get_all_stops()
    stops_clusters = get_clusters_of_stops(stops)
    return stops, stops_clusters


def test_stops_clusters_tables_created(db_file):
    cur = db_file.con.cursor()
    cur.execute('DROP TABLE IF EXISTS stops_clusters')
    cur.execute('DROP TABLE IF EXISTS stops_stops_clusters')
    db_file.upload_stops_clusters_to_db()
    cur.execute('SELECT name FROM sqlite_master WHERE type="table" AND name="stops_clusters"')
    assert cur.fetchone(), 'stops_clusters table not created'
    cur.execute('SELECT name FROM sqlite_master WHERE type="table" AND name="stops_stops_clusters"')
    assert cur.fetchone(), 'stops_stops_clusters table not created'


def test_search_stops_by_name(db_file):
    stops = db_file.search_stops("roma")

    # check if ref and name are present in each result
    is_valid = all(hasattr(stop, 'ref') and hasattr(stop, 'name') for stop in stops)

    assert is_valid, 'search_stops does not return a list of Stop objects with ref and name attributes'


def test_clusters_stops_structure(stops_and_stops_clusters):
    _, stops_clusters = stops_and_stops_clusters
    assert all(hasattr(cluster, 'name') for cluster in stops_clusters), 'not all clusters have name'
    assert all(hasattr(cluster, 'stops') for cluster in stops_clusters), 'not all clusters have stops'
    assert all(hasattr(cluster, 'lat') for cluster in stops_clusters), 'not all clusters have lat'
    assert all(hasattr(cluster, 'lon') for cluster in stops_clusters), 'not all clusters have lon'
    assert all(hasattr(cluster, 'times_count') for cluster in stops_clusters), 'not all clusters have times_count'


def test_cluster_times_count_equals_sum_of_stops_times_count(stops_and_stops_clusters):
    stops, stops_clusters = stops_and_stops_clusters
    for cluster in stops_clusters:
        assert cluster.times_count == sum(stop.times_count for stop in cluster.stops), \
            'cluster times_count is not equal to sum of stops times_count'


def test_all_stops_are_in_clusters(stops_and_stops_clusters):
    stops, stops_clusters = stops_and_stops_clusters
    flat_result = sorted(
        [stop.name.strip().upper() + '_' + stop.id for stops_cluster in stops_clusters for
         stop in stops_cluster.stops])

    actual_strings = sorted([item.name.strip().upper() + '_' + item.id for item in stops])

    assert actual_strings == flat_result, 'not all stops are in the clusters'


def test_uniqueness_of_known_clusters(stops_and_stops_clusters):
    stops, stops_clusters = stops_and_stops_clusters

    known_clusters = ['P.LE ROMA']

    for known_cluster in known_clusters:
        assert len([cluster for cluster in stops_clusters if known_cluster in cluster.name]) == 1, \
            f'more than one cluster with name "{known_cluster}"'
