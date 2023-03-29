import logging
import os
import re
import sqlite3
import ssl
import subprocess
import urllib
import urllib.request
from datetime import datetime, timedelta
from sqlite3 import Connection

import requests
from bs4 import BeautifulSoup
from geopy.distance import distance

from MuoVErsi.helpers import cluster_strings

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


def get_clusters_of_stops(stops):
    clusters = cluster_strings(stops)
    for cluster_name, stops in clusters.copy().items():
        stops = stops['stops'].copy()
        if len(stops) > 1:
            # calculate centroid of the coordinates
            latitudes = [stop['coords'][0] for stop in stops]
            longitudes = [stop['coords'][1] for stop in stops]
            centroid_lat = sum(latitudes) / len(latitudes)
            centroid_long = sum(longitudes) / len(longitudes)
            centroid = (round(centroid_lat, 7), round(centroid_long, 7))

            split_cluster = False
            for stop in stops:
                if distance(stop['coords'], centroid).m > 200:
                    split_cluster = True
                    break
            if split_cluster:
                del clusters[cluster_name]
                i = 1
                for stop in stops:
                    if stop['stop_name'] in clusters:
                        clusters[f'{stop["stop_name"]} ({i})'] = {'stops': [stop], 'coords': stop['coords'], 'times_count': stop['times_count']}
                        i += 1
                    else:
                        clusters[stop['stop_name']] = {'stops': [stop], 'coords': stop['coords'], 'times_count': stop['times_count']}
            else:
                clusters[cluster_name]['coords'] = centroid
                clusters[cluster_name]['times_count'] = sum(stop['times_count'] for stop in stops)
        else:
            clusters[cluster_name]['coords'] = stops[0]['coords']
            clusters[cluster_name]['times_count'] = stops[0]['times_count']
    return clusters


class DBFile:
    def __init__(self, transport_type, gtfs_version=None, location=''):
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

    def file_path(self, ext):
        current_dir = os.path.abspath(os.path.dirname(__file__))
        parent_dir = os.path.abspath(current_dir + f"/../{self.location}")

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

    def get_all_stops(self):
        cur = self.con.cursor()
        query = """
        SELECT S.stop_id, stop_name, stop_lat, stop_lon, count(s.stop_id) as times_count
            FROM stop_times
                     INNER JOIN stops s on stop_times.stop_id = s.stop_id
            GROUP BY s.stop_id
        """
        stops = cur.execute(query)
        return stops.fetchall()

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
        for cluster_name, cluster_values in stops_clusters.items():
            result = cur.execute('INSERT INTO stops_clusters (name, lat, lon, times_count) VALUES (?, ?, ?, ?)', (
                cluster_name, cluster_values['coords'][0], cluster_values['coords'][1], cluster_values['times_count']))
            cluster_id = result.lastrowid
            for stop in cluster_values['stops']:
                cur.execute('INSERT INTO stops_stops_clusters (stop_id, stop_cluster_id) VALUES (?, ?)',
                            (stop['stop_id'], cluster_id))
        self.con.commit()
        return True

    def search_stops(self, name=None, lat=None, lon=None):
        cur = self.con.cursor()
        if lat and lon:
            query = 'SELECT id, name FROM stops_clusters ' \
                    'ORDER BY ((lat-?)*(lat-?)) + ((lon-?)*(lon-?)) ASC LIMIT 4'
            results = cur.execute(query, (lat, lat, lon, lon)).fetchall()
        else:
            query = 'SELECT id, name FROM stops_clusters WHERE name LIKE ? ORDER BY times_count DESC LIMIT 4'
            results = cur.execute(query, (f'%{name}%',)).fetchall()

        return results

    def get_stop_times_between_stops(self, dep_stop_ids: set, arr_stop_ids: set, service_ids, line, start_time, offset_times, limit, day):
        cur = self.con.cursor()

        route = 'AND route_short_name = ?' if line != '' else ''
        departure_time = 'AND departure_time >= ?' if start_time != '' else ''
        
        query = """
        SELECT dep.departure_time      as dep_time,
               r.route_short_name     as line,
               t.trip_headsign        as headsign,
               t.trip_id              as trip_id,
               dep.stop_sequence       as stop_sequence,
               arr_time               as arr_time
        FROM stop_times dep
                 INNER JOIN (SELECT trip_id, departure_time as arr_time, stop_sequence
                             FROM stop_times
                             WHERE stop_times.stop_id in ({arr_stop_ids})
                               {departure_time}
                            ORDER BY stop_times.departure_time
                            )
                        arr ON dep.trip_id = arr.trip_id
                 INNER JOIN trips t ON dep.trip_id = t.trip_id
                 INNER JOIN routes r ON t.route_id = r.route_id
        WHERE dep.stop_id in ({dep_stop_ids})
          AND t.service_id in ({service_ids})
          AND dep.pickup_type = 0
          AND dep.stop_sequence < arr.stop_sequence
          {route}
        ORDER BY dep.departure_time, r.route_short_name, t.trip_headsign, dep.stop_sequence
        LIMIT ? OFFSET ?
        """.format(
            service_ids=','.join(['?'] * len(service_ids)),
            arr_stop_ids=','.join(['?'] * len(arr_stop_ids)),
            dep_stop_ids=','.join(['?'] * len(dep_stop_ids)),
            route=route,
            departure_time=departure_time
        )

        params = (*arr_stop_ids,)

        if start_time != '':
            start_datetime = datetime.combine(day, start_time)
            minutes_5 = start_datetime - timedelta(minutes=5)
            params += (minutes_5.strftime('%H:%M'),)

        params += (*dep_stop_ids, *service_ids)

        if line != '':
            params += (line,)

        params += (limit, offset_times)

        results = cur.execute(query, params).fetchall()

        return results, service_ids
