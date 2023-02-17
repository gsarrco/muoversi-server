import unittest
from datetime import date, time
from pprint import pprint

from MuoVErsi.db import DBFile
from MuoVErsi.helpers import times_groups, get_time
from MuoVErsi.stop_times_filter import StopTimesFilter


class FunctionsCase(unittest.TestCase):
    def test_times_groups(self):
        elements = ['21:56', '22:06', '22:16', '22:26', '22:36', '22:46', '22:56', '23:06', '23:16', '23:26', '23:36', '23:54', '24:28', '25:08']
        result = [('21:56', '22:16'), ('22:26', '22:46'), ('22:56', '23:16'), ('23:26', '23:54'), ('24:28', '25:08')]
        self.assertEqual(times_groups(elements, 5), result)


class StopTimesFilterCase(unittest.TestCase):
    def test_get_time(self):
        self.assertEqual(get_time('25:34:23'), time(1, 34, 23, 1))
        self.assertEqual(get_time('21:43:23'), time(21, 43, 23, 0))

    def test_str(self):
        stop_data1 = StopTimesFilter(123, date(2023, 1, 31), '', '', '')
        self.assertEqual(stop_data1.query_data(line='4'), '123/2023-01-31/4////0')
        stop_data2 = StopTimesFilter(123, date(2023, 1, 31), '', '', '')
        self.assertEqual(stop_data2.query_data(line='4', end_time=time(21, 12, 12)),
                         '123/2023-01-31/4//21:12:12//0')

    def test_messages(self):
        stop_data = StopTimesFilter(123, date(2023, 2, 11), '', time(23, 21), '')
        con = DBFile('automobilistico').connect_to_database()
        text, reply_markup, times_history = stop_data.format_times_text(stop_data.get_times(con), [])
        actual_text = "<b>sabato 11 febbraio 2023 - dalle 23:21</b>\nNon possiamo mostrare orari di giornate passate." \
                      " Torna alla giornata odierna o a una futura."
        self.assertEqual(text, actual_text)
        self.assertEqual(reply_markup, None)


if __name__ == '__main__':
    unittest.main()
