import logging
import os
import re
import sqlite3
import ssl
import subprocess
import urllib
import urllib.request
from datetime import datetime, timedelta, date, time
from sqlite3 import Connection

import math
import requests
from bs4 import BeautifulSoup
from telegram.ext import ContextTypes

from MuoVErsi.sources.base import Source, Stop, StopTime as BaseStopTime, Route, Direction, Station
from .clustering import get_clusters_of_stops, get_loc_from_stop_and_cluster
from .models import CStop

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


def get_latest_gtfs_version(transport_type):
    url = f"https://actv.avmspa.it/sites/default/files/attachments/opendata/{transport_type}/"

    response = requests.get(url)

    soup = BeautifulSoup(response.text, "html.parser")

    link = soup.find_all("a")[-1]
    filename = link.get('href')
    match = re.search(r'\d+', filename)
    version = int(match.group(0))
    # datetime_str = str(link.next_sibling).strip().split('            ')[0]
    # datetime_obj = datetime.strptime(datetime_str, '%d-%b-%Y %H:%M')
    return version


class GTFS(Source):
    def __init__(self, transport_type, gtfs_version=None, location='', dev=False):
        super().__init__(transport_type)
        self.transport_type = transport_type
        self.location = location

        if gtfs_version:
            self.gtfs_version = gtfs_version
            self.download_and_convert_file()
        else:
            gtfs_version = get_latest_gtfs_version(transport_type)

            for try_version in range(gtfs_version, 0, -1):
                self.gtfs_version = try_version
                self.download_and_convert_file()
                if self.get_calendar_services():
                    break

        self.con = self.connect_to_database()
        if dev:
            self.con.set_trace_callback(logger.info)

        stops_clusters_uploaded = self.upload_stops_clusters_to_db()
        logger.info('%s stops clusters uploaded: %s', self.name, stops_clusters_uploaded)

    def file_path(self, ext):
        current_dir = os.path.abspath(os.path.dirname(__file__))
        parent_dir = os.path.abspath(current_dir + f"/../../../{self.location}")

        return os.path.join(parent_dir, f'{self.transport_type}_{self.gtfs_version}.{ext}')

    def download_and_convert_file(self, force=False):
        if os.path.isfile(self.file_path('db')) and not force:
            return

        url = f'https://actv.avmspa.it/sites/default/files/attachments/opendata/' \
              f'{self.transport_type}/actv_{self.transport_type[:3]}_{self.gtfs_version}.zip'
        ssl._create_default_https_context = ssl._create_unverified_context
        file_path = self.file_path('zip')
        logger.info('Downloading %s to %s', url, file_path)
        urllib.request.urlretrieve(url, file_path)

        subprocess.run(["gtfs-import", "--gtfsPath", self.file_path('zip'), '--sqlitePath', self.file_path('db')])

    def get_calendar_services(self) -> list[str]:
        today_ymd = datetime.today().strftime('%Y%m%d')
        weekday = datetime.today().strftime('%A').lower()
        with self.connect_to_database() as con:
            cur = con.cursor()
            services = cur.execute(
                f'SELECT service_id FROM calendar WHERE {weekday} = 1 AND start_date <= ? AND end_date >= ?',
                (today_ymd, today_ymd))

            return list(set([service[0] for service in services.fetchall()]))

    def connect_to_database(self) -> Connection:
        return sqlite3.connect(self.file_path('db'))

    def get_all_stops(self) -> list[CStop]:
        cur = self.con.cursor()
        query = """
        SELECT S.stop_id, stop_name, stop_lat, stop_lon, count(s.stop_id) as times_count
            FROM stop_times
                     INNER JOIN stops s on stop_times.stop_id = s.stop_id
            GROUP BY s.stop_id
        """
        stops = cur.execute(query).fetchall()
        return [CStop(*stop) for stop in stops]

    def upload_stops_clusters_to_db(self, force=False) -> bool:
        cur = self.con.cursor()
        if not force:
            # Check if stops_clusters table does not exist
            cur.execute('SELECT name FROM sqlite_master WHERE type="table" AND name="stops_clusters"')
            if cur.fetchone():
                return False

        logger.info('Uploading stops clusters to db')
        cur.execute('DROP TABLE IF EXISTS stops_clusters')
        cur.execute('''
            CREATE TABLE stops_clusters (
                id INTEGER PRIMARY KEY, 
                name TEXT, 
                lat REAL, 
                lon REAL, 
                times_count INTEGER,
                UNIQUE (name)
            )
        ''')
        # create a one-to-many relation between stops and stops_clusters
        cur.execute('DROP TABLE IF EXISTS stops_stops_clusters')
        cur.execute('''
            CREATE TABLE stops_stops_clusters (
                id INTEGER PRIMARY KEY,
                stop_id INTEGER,
                stop_cluster_id INTEGER,
                FOREIGN KEY (stop_id) REFERENCES stops (stop_id),
                FOREIGN KEY (stop_cluster_id) REFERENCES stops_clusters (id)
            )
        ''')
        stops = self.get_all_stops()
        stops_clusters = get_clusters_of_stops(stops)
        total_times_count = sum([cluster.times_count for cluster in stops_clusters])

        new_stations = []

        for cluster in stops_clusters:
            times_count = round(cluster.times_count / total_times_count,
                                int(math.log10(total_times_count)) + 1)
            ids = ','.join([str(stop.id) for stop in cluster.stops])
            station = Station(id=cluster.name, name=cluster.name, lat=cluster.lat, lon=cluster.lon, ids=ids,
                              times_count=times_count, source=self.name)
            new_stations.append(station)

            result = cur.execute('INSERT INTO stops_clusters (name, lat, lon, times_count) VALUES (?, ?, ?, ?)', (
                cluster.name, cluster.lat, cluster.lon, cluster.times_count))
            cluster_id = result.lastrowid
            for stop in cluster.stops:
                cur.execute('INSERT INTO stops_stops_clusters (stop_id, stop_cluster_id) VALUES (?, ?)',
                            (stop.id, cluster_id))
        self.con.commit()
        self.sync_stations_db(new_stations)
        return True

    def search_stops(self, name=None, lat=None, lon=None, limit=4) -> list[Stop]:
        cur = self.con.cursor()
        if lat and lon:
            query = 'SELECT id, name FROM stops_clusters ' \
                    'ORDER BY ((lat-?)*(lat-?)) + ((lon-?)*(lon-?)) LIMIT ?'
            results = cur.execute(query, (lat, lat, lon, lon, limit)).fetchall()
        else:
            query = 'SELECT id, name FROM stops_clusters WHERE name LIKE ? ORDER BY times_count DESC LIMIT ?'
            results = cur.execute(query, (f'%{name}%', limit)).fetchall()

        stops = []
        for result in results:
            stops.append(Stop(result[0], result[1]))

        return stops

    def get_stop_times(self, stop: Stop, line, start_time, day,
                       offset_times, context: ContextTypes.DEFAULT_TYPE | None = None, count=False):
        cur = self.con.cursor()

        route_name, route_id = line.split('-') if '-' in line else (line, '')
        if route_id == '':
            line = route_name
            route = 'AND route_short_name = ?' if line != '' else ''
        else:
            line = route_id
            route = 'AND r.route_id = ?'

        today_service_ids = self.get_active_service_ids(day, context)

        day_start = datetime.combine(day, time(0))

        if start_time == '':
            start_dt = day_start
        else:
            start_dt = max(day_start, datetime.combine(day, start_time) - timedelta(minutes=self.MINUTES_TOLERANCE))

        or_other_service = ''
        yesterday_service_ids = []
        if start_dt.hour < 6:
            yesterday_service_ids = self.get_active_service_ids(day - timedelta(days=1), context)
            if yesterday_service_ids:
                or_other_service_ids = ','.join(['?'] * len(yesterday_service_ids))
                or_other_service = f'OR (dep.departure_time >= ? AND t.service_id in ({or_other_service_ids}))'
            else:
                start_dt = datetime.combine(day, time(6))

        if count:
            select_elements = "r.route_short_name     as line"
            button_elements = "GROUP BY route_short_name ORDER BY count(*) DESC"
        else:
            select_elements = """
                dep.departure_time      as dep_time,
                r.route_short_name     as line,
                hs_cluster_name        as headsign,
                t.trip_id              as trip_id,
                dep.stop_sequence       as stop_sequence,
                s.stop_name          as dep_stop_name,
                CAST(SUBSTR(dep.departure_time, 1, 2) AS INTEGER) % 24 dep_hour_normalized,
                CAST(SUBSTR(dep.departure_time, 4, 2) AS INTEGER) dep_minute"""
            button_elements = """
                ORDER BY dep_hour_normalized, dep_minute, r.route_short_name, t.trip_headsign, dep.stop_sequence
                LIMIT ? OFFSET ?"""

        query = f"""
                SELECT {select_elements}
                FROM stop_times dep
                         INNER JOIN (SELECT trip_id, stops_clusters.name as hs_cluster_name
                                     FROM stop_times st
                                        INNER JOIN stops ON st.stop_id = stops.stop_id
                                        INNER JOIN stops_stops_clusters ON stops.stop_id = stops_stops_clusters.stop_id
                                        INNER JOIN stops_clusters ON stops_stops_clusters.stop_cluster_id = stops_clusters.id
                                    WHERE st.stop_sequence = (
                                        SELECT MAX(stop_times.stop_sequence) 
                                        FROM stop_times 
                                        WHERE stop_times.trip_id = st.trip_id
                                    )
                                    )
                                hs ON dep.trip_id = hs.trip_id
                         INNER JOIN trips t ON dep.trip_id = t.trip_id
                         INNER JOIN routes r ON t.route_id = r.route_id
                         INNER JOIN stops s ON dep.stop_id = s.stop_id
                WHERE dep.stop_id in ({','.join(['?'] * len(stop.ids))})
                  AND ((t.service_id in ({','.join(['?'] * len(today_service_ids))}) AND dep.departure_time >= ? 
                  AND dep.departure_time <= ?) 
                  {or_other_service})
                  AND dep.pickup_type = 0
                  {route}
                {button_elements}
                """

        params = (*stop.ids, *today_service_ids, start_dt.strftime('%H:%M'), '23:59')

        if or_other_service != '':
            # in the string add 24 hours to start_dt time
            start_time_25 = f'{start_dt.hour + 24:02}:{start_dt.minute:02}'
            params += (start_time_25, *yesterday_service_ids)

        if line != '':
            params += (line,)

        if not count:
            params += (self.LIMIT, offset_times)

        results = cur.execute(query, params).fetchall()

        if count:
            return [line[0] for line in cur.execute(query, params).fetchall()]

        stop_times = []
        for result in results:
            location = get_loc_from_stop_and_cluster(result[5], stop.name)
            dep_dt = datetime.combine(day, time(result[6], result[7]))
            stop_time = BaseStopTime(stop, dep_dt, dep_dt, result[4], 0, location, result[2], result[3], result[1])
            stop_times.append(stop_time)

        return stop_times

    def get_stop_times_between_stops(self, dep_stop: Stop, arr_stop: Stop, line, start_time,
                                     offset_times, day,
                                     context: ContextTypes.DEFAULT_TYPE | None = None, count=False):
        cur = self.con.cursor()

        route_name, route_id = line.split('-') if '-' in line else (line, '')
        if route_id == '':
            line = route_name
            route = 'AND route_short_name = ?' if line != '' else ''
        else:
            line = route_id
            route = 'AND r.route_id = ?'

        today_service_ids = self.get_active_service_ids(day, context)

        day_start = datetime.combine(day, time(0))

        if start_time == '':
            start_dt = day_start
        else:
            start_dt = max(day_start, datetime.combine(day, start_time) - timedelta(minutes=self.MINUTES_TOLERANCE))

        or_other_service = ''
        yesterday_service_ids = []
        if start_dt.hour < 6:
            yesterday_service_ids = self.get_active_service_ids(day - timedelta(days=1), context)
            if yesterday_service_ids:
                or_other_service_ids = ','.join(['?'] * len(yesterday_service_ids))
                or_other_service = f'OR (dep.departure_time >= ? AND t.service_id in ({or_other_service_ids}))'
            else:
                start_dt = datetime.combine(day, time(6))

        if count:
            select_elements = "r.route_short_name     as line"
            button_elements = "GROUP BY route_short_name ORDER BY count(*) DESC"
        else:
            select_elements = """
                   dep.departure_time      as dep_time,
                   r.route_short_name     as line,
                   hs_cluster_name        as headsign,
                   t.trip_id              as trip_id,
                   dep.stop_sequence       as stop_sequence,
                   arr_time               as arr_time,
                   s.stop_name          as dep_stop_name,
                   arr_stop_name          as arr_stop_name,
                   CAST(SUBSTR(dep.departure_time, 1, 2) AS INTEGER) % 24 dep_hour_normalized,
                   CAST(SUBSTR(dep.departure_time, 4, 2) AS INTEGER) dep_minute,
                   CAST(SUBSTR(arr_time, 1, 2) AS INTEGER) % 24 arr_hour_normalized,
                   CAST(SUBSTR(arr_time, 4, 2) AS INTEGER) arr_minute
            """
            button_elements = """
                ORDER BY dep_hour_normalized, dep_minute, r.route_short_name, t.trip_headsign, dep.stop_sequence
                LIMIT ? OFFSET ?
            """

        query = f"""
        SELECT {select_elements}
        FROM stop_times dep
                 INNER JOIN (SELECT trip_id, departure_time as arr_time, stop_sequence, stop_name as arr_stop_name
                             FROM stop_times
                                INNER JOIN stops ON stop_times.stop_id = stops.stop_id
                             WHERE stop_times.stop_id in ({','.join(['?'] * len(arr_stop.ids))})
                            ORDER BY stop_times.departure_time
                            )
                        arr ON dep.trip_id = arr.trip_id
                 INNER JOIN (SELECT trip_id, stops_clusters.name as hs_cluster_name
                     FROM stop_times st
                        INNER JOIN stops ON st.stop_id = stops.stop_id
                        INNER JOIN stops_stops_clusters ON stops.stop_id = stops_stops_clusters.stop_id
                        INNER JOIN stops_clusters ON stops_stops_clusters.stop_cluster_id = stops_clusters.id
                    WHERE st.stop_sequence = (
                        SELECT MAX(stop_times.stop_sequence) 
                        FROM stop_times 
                        WHERE stop_times.trip_id = st.trip_id
                    )
                    )
                 hs ON dep.trip_id = hs.trip_id
                 INNER JOIN trips t ON dep.trip_id = t.trip_id
                 INNER JOIN routes r ON t.route_id = r.route_id
                 INNER JOIN stops s ON dep.stop_id = s.stop_id
        WHERE dep.stop_id in ({','.join(['?'] * len(dep_stop.ids))})
          AND ((t.service_id in ({','.join(['?'] * len(today_service_ids))}) AND dep.departure_time >= ? 
          AND dep.departure_time <= ?) 
          {or_other_service})
          AND dep.pickup_type = 0
          AND dep.stop_sequence < arr.stop_sequence
          {route}
        {button_elements}
        """

        params = (*arr_stop.ids, *dep_stop.ids, *today_service_ids, start_dt.strftime('%H:%M'), '23:59')

        if or_other_service != '':
            # in the string add 24 hours to start_dt time
            start_time_25 = f'{start_dt.hour + 24:02}:{start_dt.minute:02}'
            params += (start_time_25, *yesterday_service_ids)

        if line != '':
            params += (line,)

        if not count:
            params += (self.LIMIT, offset_times)

        results = cur.execute(query, params).fetchall()

        if count:
            return [line[0] for line in cur.execute(query, params).fetchall()]

        directions = []

        for result in results:
            dep_dt = datetime.combine(day, time(result[8], result[9]))
            dep_location = get_loc_from_stop_and_cluster(result[6], dep_stop.name)
            dep_stop_time = BaseStopTime(dep_stop, dep_dt, dep_dt, result[4], 0, dep_location, result[2], result[3],
                                         result[1])
            arr_time = time(result[10], result[11])
            if arr_time < dep_dt.time():
                arr_dt = datetime.combine(day + timedelta(days=1), arr_time)
            else:
                arr_dt = datetime.combine(day, arr_time)
            arr_location = get_loc_from_stop_and_cluster(result[7], arr_stop.name)
            arr_stop_time = BaseStopTime(arr_stop, arr_dt, arr_dt, result[4], 0, arr_location, result[2], result[3],
                                         result[1])
            route = Route(dep_stop_time, arr_stop_time)
            directions.append(Direction([route]))

        return directions

    def get_stop_from_ref(self, ref) -> Stop:
        # get stop name
        cur = self.con.cursor()
        results = cur.execute('SELECT name FROM stops_clusters WHERE id = ?', (ref,)).fetchall()
        name = results[0][0]

        # get stop ids
        cur = self.con.cursor()
        results = cur.execute('SELECT stop_id FROM stops_stops_clusters WHERE stop_cluster_id = ?',
                              (ref,)).fetchall()
        ids = [result[0] for result in results]

        return Stop(ref, name, ids)

    def search_lines(self, name, context: ContextTypes.DEFAULT_TYPE | None = None):
        today = date.today()
        service_ids = self.get_active_service_ids(today, context)

        cur = self.con.cursor()
        query = """SELECT trips.trip_id, route_short_name, route_long_name, routes.route_id
                            FROM stop_times
                                INNER JOIN trips ON stop_times.trip_id = trips.trip_id
                                INNER JOIN routes ON trips.route_id = routes.route_id
                            WHERE route_short_name = ?
                                AND trips.service_id in ({seq})
                            GROUP BY routes.route_id ORDER BY count(stop_times.id) DESC;""".format(
            seq=','.join(['?'] * len(service_ids)))

        results = cur.execute(query, (name, *service_ids)).fetchall()
        return results

    def get_active_service_ids(self, day: date, context: ContextTypes.DEFAULT_TYPE | None = None) -> tuple:
        today_ymd = day.strftime('%Y%m%d')

        if context:
            # access safely context.bot_data['service_ids'][self.name][today_ymd]
            service_ids = context.bot_data.setdefault('service_ids', {}).setdefault(self.name, {}).setdefault(today_ymd,
                                                                                                              None)
            if service_ids:
                logger.info(f'Using cached service_ids for {today_ymd}')
                return service_ids

        weekday = day.strftime('%A').lower()

        cur = self.con.cursor()
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

        if context:
            context.bot_data.setdefault('service_ids', {}).setdefault(self.name, {})[today_ymd] = service_ids
            logger.info(f'Cached service_ids for {today_ymd}')

        return service_ids

    def get_stops_from_trip_id(self, trip_id, day: date) -> list[BaseStopTime]:
        cur = self.con.cursor()
        cur.row_factory = sqlite3.Row
        results = cur.execute('''
            SELECT
                sc.id as sc_id,
                sc.name as sc_name,
                sp.stop_id as sp_id,
                sp.stop_name as sp_name,
                CAST(SUBSTR(st.departure_time, 1, 2) AS INTEGER) % 24 dep_hour_normalized,
                CAST(SUBSTR(st.departure_time, 4, 2) AS INTEGER) dep_minute,
                r.route_short_name as route_name    
            FROM stop_times st
                     INNER JOIN stops sp ON sp.stop_id = st.stop_id
                     LEFT JOIN stops_stops_clusters ssc on sp.stop_id = ssc.stop_id
                     LEFT JOIN stops_clusters sc on ssc.stop_cluster_id = sc.id
                     LEFT JOIN trips t on st.trip_id = t.trip_id
                     LEFT JOIN routes r on t.route_id = r.route_id
            WHERE st.trip_id = ?
            ORDER BY st.stop_sequence
        ''', (trip_id,)).fetchall()

        stop_times = []
        headsign = results[-1]['sc_name']

        for result in results:
            stop = Stop(result['sc_id'], result['sc_name'], [int(result['sp_id'])])
            location = get_loc_from_stop_and_cluster(result['sp_name'], stop.name)
            dep_time = datetime.combine(day, time(result['dep_hour_normalized'], result['dep_minute']))
            stop_time = BaseStopTime(stop, dep_time, dep_time, None, 0, location, headsign, trip_id,
                                     result['route_name'])
            stop_times.append(stop_time)

        return stop_times
