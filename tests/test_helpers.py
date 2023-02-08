import unittest
from datetime import date, time

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
        stop_data1 = StopData('6021', date(2023, 1, 31), '', '', '')
        self.assertEqual(stop_data1.query_data(line='4'), '6021/2023-01-31/4//')
        stop_data2 = StopData('6021', date(2023, 1, 31), '', '', '')
        self.assertEqual(stop_data2.query_data(line='4', end_time=time(21, 12, 12)),
                         '6021/2023-01-31/4//21:12:12')


if __name__ == '__main__':
    unittest.main()
