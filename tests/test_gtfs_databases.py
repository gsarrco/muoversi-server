import os
import unittest
from datetime import datetime

from freezegun import freeze_time

from MuoVErsi.db import DBFile, get_latest_gtfs_version


class GTFSDatabasesCase(unittest.TestCase):

    def test_download_file_aut(self):
        db_file = DBFile('automobilistico', 639)
        db_file.download_and_convert_file(force=True)
        current_dir = os.path.abspath(os.path.dirname(__file__))
        parent_dir = os.path.abspath(current_dir + "/../")
        self.assertEqual(os.path.isfile(parent_dir + "/automobilistico_639.zip"), True)
        self.assertEqual(os.path.isfile(parent_dir + "/automobilistico_639.db"), True)

    def test_download_file_nav(self):
        db_file = DBFile('navigazione', 541)
        db_file.download_and_convert_file(force=True)
        current_dir = os.path.abspath(os.path.dirname(__file__))
        parent_dir = os.path.abspath(current_dir + "/../")
        self.assertEqual(os.path.isfile(parent_dir + "/navigazione_541.zip"), True)
        self.assertEqual(os.path.isfile(parent_dir + "/navigazione_541.db"), True)

    @freeze_time("2023-02-04")
    def test_db_prev_version(self):
        db_file = DBFile('automobilistico')
        self.assertEqual(db_file.gtfs_version, 638)
        self.assertEqual(db_file.transport_type, 'automobilistico')

    @freeze_time("2023-02-05")
    def test_db_curr_version(self):
        db_file = DBFile('automobilistico')
        self.assertEqual(db_file.gtfs_version, 639)
        self.assertEqual(db_file.transport_type, 'automobilistico')

    def test_get_latest_gtfs_version(self):
        self.assertEqual(get_latest_gtfs_version('automobilistico'), 639)


if __name__ == '__main__':
    unittest.main()
