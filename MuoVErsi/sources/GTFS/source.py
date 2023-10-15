import logging
import math
import os
import re
import sqlite3
import ssl
import subprocess
import urllib
import urllib.request
from datetime import datetime, timedelta, date, time
from sqlite3 import Connection

import requests
from bs4 import BeautifulSoup
from telegram.ext import ContextTypes
from tqdm import tqdm

from MuoVErsi.sources.base import Source, BaseStopTime, Route, Direction, Station, Stop, TripStopTime
from .clustering import get_clusters_of_stops, get_loc_from_stop_and_cluster
from .models import CStop

from sqlalchemy import or_, select, func

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
    def __init__(self, transport_type, emoji, session, typesense, gtfs_versions_range: tuple[int] = None, location='', dev=False, ref_dt: datetime = None):
        super().__init__(transport_type[:3], emoji, session, typesense)
        self.transport_type = transport_type
        self.location = location
        self.service_ids = {}

        if gtfs_versions_range:
            init_version = gtfs_versions_range[0]
        else:
            init_version = get_latest_gtfs_version(transport_type)

        fin_version = gtfs_versions_range[1] if gtfs_versions_range else 0

        if not ref_dt:
            ref_dt = datetime.today()

        for try_version in range(init_version, fin_version-1, -1):
            self.download_and_convert_file(try_version)
            service_start_date = self.get_service_start_date(ref_dt, try_version)
            if service_start_date and service_start_date <= ref_dt.date():
                self.gtfs_version = try_version
                break

        if not hasattr(self, 'gtfs_version'):
            raise Exception(f'No valid GTFS version found for {transport_type}')

        self.con = self.connect_to_database(self.gtfs_version)

        stops_clusters_uploaded = self.upload_stops_clusters_to_db()
        logger.info('%s stops clusters uploaded: %s', self.name, stops_clusters_uploaded)

    def file_path(self, ext, gtfs_version):
        current_dir = os.path.abspath(os.path.dirname(__file__))
        parent_dir = os.path.abspath(current_dir + f"/../../../{self.location}")

        return os.path.join(parent_dir, f'{self.transport_type}_{gtfs_version}.{ext}')

    def download_and_convert_file(self, gtfs_version, force=False):
        if os.path.isfile(self.file_path('db', gtfs_version)) and not force:
            return

        url = f'https://actv.avmspa.it/sites/default/files/attachments/opendata/' \
              f'{self.transport_type}/actv_{self.transport_type[:3]}_{gtfs_version}.zip'
        ssl._create_default_https_context = ssl._create_unverified_context
        file_path = self.file_path('zip', gtfs_version)
        logger.info('Downloading %s to %s', url, file_path)
        urllib.request.urlretrieve(url, file_path)

        subprocess.run(["gtfs-import", "--gtfsPath", self.file_path('zip', gtfs_version), '--sqlitePath', self.file_path('db', gtfs_version)])

    def get_service_start_date(self, ref_dt, gtfs_version) -> date:
        today_ymd = ref_dt.strftime('%Y%m%d')
        weekday = ref_dt.strftime('%A').lower()
        with self.connect_to_database(gtfs_version) as con:
            con.row_factory = sqlite3.Row
            cur = con.cursor()
            service = cur.execute(
                f'SELECT start_date FROM calendar WHERE {weekday} = 1 AND start_date <= ? AND end_date >= ? ORDER BY start_date ASC LIMIT 1',
                (today_ymd, today_ymd)).fetchone()
            
            if not service:
                return None
            
            return datetime.strptime(str(service['start_date']), '%Y%m%d').date()

    def connect_to_database(self, gtfs_version) -> Connection:
        return sqlite3.connect(self.file_path('db', gtfs_version))

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
    
    def get_all_stop_times(self, day) -> list[TripStopTime]:
        stop_times = []
        
        return stop_times
    
    def save_data(self):
        self.upload_stops_clusters_to_db(force=True)

        now = datetime.now()

        # define parameters for get_sqlite_stop_times
        all_params = (
            (now.date(), now.time(), time(23, 59)),
            (now.date() + timedelta(days=1), time(0, 0), time(23, 59)),
            (now.date() + timedelta(days=2), time(0, 0), now.time())
        )

        limit = 30000

        for params in all_params:
            offset = 0
            while True:
                stop_times = self.get_sqlite_stop_times(*params, limit, offset)
                for stop_time in tqdm(stop_times, desc = f'Uploading {self.name} stop_times of day {params[0]}'):
                    self.upload_trip_stop_time_to_postgres(stop_time)
                if len(stop_times) < limit:
                    break
                offset += limit

    def upload_stops_clusters_to_db(self, force=False) -> bool:
        cur = self.con.cursor()
        if not force:
            # Check if stops_clusters table does not exist
            cur.execute('SELECT name FROM sqlite_master WHERE type="table" AND name="stops_clusters"')
            if cur.fetchone():
                return False

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
        new_stops = []

        for cluster in stops_clusters:
            times_count = round(cluster.times_count / total_times_count,
                                int(math.log10(total_times_count)) + 1)
            ids = ','.join([str(stop.id) for stop in cluster.stops])
            station = Station(id=cluster.name, name=cluster.name, lat=cluster.lat, lon=cluster.lon, ids=ids,
                              times_count=times_count, source=self.name)
            new_stations.append(station)

            for stop in cluster.stops:
                platform = get_loc_from_stop_and_cluster(stop.name)
                platform = platform if platform != '' else None
                id_ = self.name + '_' + stop.id if self.name != 'treni' else stop.id
                stop = Stop(id=id_, platform=platform, lat=stop.lat, lon=stop.lon, station_id=cluster.name, source=self.name)
                new_stops.append(stop)

            result = cur.execute('INSERT INTO stops_clusters (name, lat, lon, times_count) VALUES (?, ?, ?, ?)', (
                cluster.name, cluster.lat, cluster.lon, cluster.times_count))
            cluster_id = result.lastrowid
            for stop in cluster.stops:
                cur.execute('INSERT INTO stops_stops_clusters (stop_id, stop_cluster_id) VALUES (?, ?)',
                            (stop.id, cluster_id))
        self.con.commit()
        self.sync_stations_db(new_stations, new_stops)
        return True

    def get_sqlite_stop_times(self, day: date, start_time: time, end_time: time, limit: int, offset: int) -> list[TripStopTime]:
        cur = self.con.cursor()

        today_service_ids = self.get_active_service_ids(day)

        start_dt = datetime.combine(day, start_time)
        end_dt = datetime.combine(day, end_time)

        or_other_service = ''
        yesterday_service_ids = []
        if start_dt.hour < 6:
            yesterday_service_ids = self.get_active_service_ids(day - timedelta(days=1))
            if yesterday_service_ids:
                or_other_service_ids = ','.join(['?'] * len(yesterday_service_ids))
                or_other_service = f'OR (dep.departure_time >= ? AND t.service_id in ({or_other_service_ids}))'
            else:
                start_dt = datetime.combine(day, time(6))

        select_elements = """
            dep.departure_time      as dep_time,
            r.route_short_name     as line,
            dep.stop_headsign        as headsign,
            t.trip_id              as trip_id,
            dep.stop_sequence       as stop_sequence,
            s.stop_name          as dep_stop_name,
            CAST(SUBSTR(dep.departure_time, 1, 2) AS INTEGER) % 24 dep_hour_normalized,
            CAST(SUBSTR(dep.departure_time, 4, 2) AS INTEGER) dep_minute,
            orig_stop_id           as orig_stop_id,
            CAST(SUBSTR(orig_dep_time, 1, 2) AS INTEGER) % 24 orig_dep_hour_normalized,
            CAST(SUBSTR(orig_dep_time, 4, 2) AS INTEGER) orig_dep_minute,
            dep.stop_id as dep_stop_id,
            dep.pickup_type as dep_pickup_type"""

        query = f"""
                SELECT {select_elements}
                FROM stop_times dep
                         INNER JOIN (SELECT trip_id, departure_time as orig_dep_time, stop_id as orig_stop_id
                             FROM stop_times
                             WHERE stop_sequence = 1
                            )
                         orig ON dep.trip_id = orig.trip_id
                         INNER JOIN trips t ON dep.trip_id = t.trip_id
                         INNER JOIN routes r ON t.route_id = r.route_id
                         INNER JOIN stops s ON dep.stop_id = s.stop_id
                WHERE ((t.service_id in ({','.join(['?'] * len(today_service_ids))}) AND dep.departure_time >= ? 
                  AND dep.departure_time <= ?) 
                  {or_other_service})
                LIMIT ? OFFSET ?
                """

        params = (*today_service_ids, start_dt.strftime('%H:%M'), end_dt.strftime('%H:%M'))

        if or_other_service != '':
            # in the string add 24 hours to start_dt time
            start_time_25 = f'{start_dt.hour + 24:02}:{start_dt.minute:02}'
            params += (start_time_25, *yesterday_service_ids)

        params += (limit, offset)

        results = cur.execute(query, params).fetchall()

        stop_times = []
        for result in results:
            location = get_loc_from_stop_and_cluster(result[5])
            dep_time = time(result[6], result[7])
            dep_dt = datetime.combine(day, dep_time)
            arr_dt = dep_dt
            orig_dep_time = time(result[9], result[10])
            orig_dep_date = day if orig_dep_time <= dep_time else day - timedelta(days=1)
            headsign = result[2] if result[2] else ''
            stop = Station(id=result[11])

            if result[4] == 1:
                arr_dt = None
            if result[12] == 1:
                dep_dt = None

            stop_time = TripStopTime(stop, result[8], dep_dt, result[4], 0, location, headsign, result[3], result[1], arr_dt, orig_dep_date, headsign)
            stop_times.append(stop_time)

        return stop_times

    def search_lines(self, name):
        today = date.today()
        from MuoVErsi.sources.base import Trip
        trips = self.session.execute(
            select(func.max(Trip.number), Trip.dest_text)\
            .filter(Trip.orig_dep_date == today)\
            .filter(Trip.route_name == name)\
            .group_by(Trip.dest_text)\
            .order_by(func.count(Trip.id).desc()))\
            .all()
        
        results = [(trip[0], name, trip[1]) for trip in trips]

        return results

    def get_active_service_ids(self, day: date) -> tuple:
        today_ymd = day.strftime('%Y%m%d')

        # access safely context.bot_data['service_ids'][self.name][today_ymd]
        service_ids = self.service_ids.setdefault(today_ymd, None)
        if service_ids:
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

        self.service_ids[today_ymd] = service_ids

        return service_ids
