import unittest
from datetime import date, time

from MuoVErsi.db import DBFile
from MuoVErsi.helpers import times_groups, StopData, get_time, search_stops


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

    def test_messages(self):
        stop_data = StopData('1005', date(2023, 2, 11), '', time(23, 21), '')
        con = DBFile('automobilistico').connect_to_database()
        text, reply_markup, times_history = stop_data.format_times_text(stop_data.get_times(con), [])
        actual_text = "sabato 11 febbraio 2023 - dalle 23:21\n\nNessun orario trovato per questa giornata." \
                      "\nCambia giorno con i pulsanti -1g e +1g, oppure cambia fermata."
        self.assertEqual(text, actual_text)
        self.assertEqual(reply_markup, None)

    def test_search_stops_by_name(self):
        con = DBFile('automobilistico', 640).connect_to_database()
        con.set_trace_callback(print)
        results = search_stops(con, "mestre centro")

        if isinstance(results, list):
            is_valid = all(isinstance(elem, tuple) and len(elem) == 2 for elem in results)
        else:
            is_valid = False

        self.assertEqual(is_valid, True)


if __name__ == '__main__':
    unittest.main()
