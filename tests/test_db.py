from datetime import datetime
import pytest

from MuoVErsi.sources.GTFS import GTFS, get_clusters_of_stops, CCluster, CStop


@pytest.fixture
def db_file():
    ref_dt = datetime(2023, 10, 15)
    return GTFS('navigazione', '⛴️', None, None, (558, 557), 'tests/data', ref_dt=ref_dt)


def test_valid_gtfs():
    _558_ref_df = datetime(2023, 10, 7)
    _558_gtfs = GTFS('navigazione', '⛴️', None, None, (558, 557), 'tests/data', ref_dt=_558_ref_df)
    assert _558_gtfs.gtfs_version == 558, 'invalid gtfs version'

    _557_ref_dt = datetime(2023, 10, 6)
    _557_gtfs = GTFS('navigazione', '⛴️', None, None, (558, 557), 'tests/data', ref_dt=_557_ref_dt)
    assert _557_gtfs.gtfs_version == 557, 'invalid gtfs version'

def test_invalid_gtfs():
    invalid_ref_df = datetime(2023, 9, 30)
    with pytest.raises(Exception):
        GTFS('navigazione', '⛴️', None, None, (558, 557), 'tests/data', ref_dt=invalid_ref_df)

@pytest.fixture
def stops_and_stops_clusters(db_file) -> tuple[list[CStop], list[CCluster]]:
    stops = db_file.get_all_stops()
    stops_clusters = get_clusters_of_stops(stops)
    return stops, stops_clusters


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
    known_clusters = ['P.le Roma', 'Lido S.M.E.', 'S. Marco-S. Zaccaria']

    for known_cluster in known_clusters:
        found_clusters = [cluster for cluster in stops_clusters if known_cluster in cluster.name]
        assert len(found_clusters) == 1, \
            f'more than one cluster with name "{known_cluster}"'
