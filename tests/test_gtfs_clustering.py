import pytest

from server.GTFS.clustering import get_root_from_stop_name, get_loc_from_stop_and_cluster


@pytest.fixture
def test_data() -> list[tuple[str, str, str]]:
    return [
        ('P.le Roma "A"', 'P.le Roma', 'A'),
        ('Mestre Centro B1', 'Mestre Centro', 'B1'),
        ('VENEZIA CORSIA C', 'VENEZIA Piazzale Roma', 'CORSIA C'),
        ('Trieste Stazione FS', 'Trieste Stazione FS', ''),
        ('Stazione MESTRE FS C1', 'Stazione MESTRE FS', 'C1'),
        ('San Marco-San Zaccaria"A"', 'S. Marco-S. Zaccaria', 'A'),
        ('Favretti MESTRE FS C2', 'Stazione MESTRE FS', 'C2')
    ]


def test_get_root_from_stop_name(test_data):
    for test_datum in test_data:
        assert get_root_from_stop_name(test_datum[0]) == test_datum[1], f'Failed for {test_datum[0]}'


def test_get_loc_from_stop_and_cluster(test_data):
    for test_datum in test_data:
        assert get_loc_from_stop_and_cluster(test_datum[0]) == test_datum[
            2], f'Failed for {test_datum[0]}'
