import unittest
from datetime import date, time

import base62

from MuoVErsi.helpers import times_groups, StopData, get_time


class FunctionsCase(unittest.TestCase):
    def test_times_groups(self):
        elements = ['21:56', '22:06', '22:16', '22:26', '22:36', '22:46', '22:56', '23:06', '23:16', '23:26', '23:36', '23:54', '24:28', '25:08']
        result = [('21:56', '22:16'), ('22:26', '22:46'), ('22:56', '23:16'), ('23:26', '23:54'), ('24:28', '25:08')]
        self.assertEqual(times_groups(elements, 5), result)


class StopDataCase(unittest.TestCase):
    def test_get_time(self):
        self.assertEqual(get_time('25:34:23'), time(1, 34, 23, 1))
        self.assertEqual(get_time('21:43:23'), time(21, 43, 23, 0))

    def test_str(self):
        stop_data1 = StopData()
        stop_data1.stop_id = '6021'
        stop_data1.day = date(2023, 1, 31)
        stop_data1.line = ''
        stop_data1.start_time = time(0, 0, 0)
        stop_data1.end_time = time(23, 59, 59)
        self.assertEqual(stop_data1.query_data(line='4'), '6021/2023-01-31/4/00:00:00/23:59:59')
        stop_data2 = StopData()
        stop_data2.stop_id = '6021'
        stop_data2.day = date(2023, 1, 31)
        stop_data2.line = ''
        stop_data2.start_time = time(0, 0, 0)
        stop_data2.end_time = time(23, 59, 59)
        self.assertEqual(stop_data2.query_data(line='4', end_time=time(21, 12, 12)),
                         '6021/2023-01-31/4/00:00:00/21:12:12')


if __name__ == '__main__':
    unittest.main()
