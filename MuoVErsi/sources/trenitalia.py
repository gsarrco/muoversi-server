import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta
from sqlite3 import Connection
from urllib.parse import quote

import requests

from MuoVErsi.sources.base import Source, Stop, StopTime

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

class Trenitalia(Source):
    def __init__(self, location=''):
        self.location = location
        super().__init__('treni')

        if os.path.exists(self.file_path()):
            self.con = self.connect_to_database()
        else:
            self.con = self.connect_to_database()
            self.populate_db()

    def connect_to_database(self) -> Connection:
        return sqlite3.connect(self.file_path())

    def populate_db(self):
        # create table "stations" in database if not exists
        cur = self.con.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS stations (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                region_code INTEGER,
                lat REAL,
                lon REAL
                )
            """
        )

        current_dir = os.path.abspath(os.path.dirname(__file__))
        datadir = os.path.abspath(current_dir + '/data')

        with open(os.path.join(datadir, 'stationIDS.json')) as f:
            station_ids = json.load(f)

        with open(os.path.join(datadir, 'stations_coords.json')) as f:
            stations_coords = json.load(f)

        for station_id, station_name in station_ids.items():
            # get values from stations_coords only if station_id is present
            station_coords = stations_coords.get(station_id, {})
            region_code = station_coords.get('region_code', None)
            lat = station_coords.get('lat', None)
            lon = station_coords.get('lon', None)

            # insert values into stations table
            cur.execute("""
                INSERT INTO stations (id, name, region_code, lat, lon)
                VALUES (?, ?, ?, ?, ?)
                """,
                (station_id, station_name, region_code, lat, lon)
            )

        self.con.commit()

    def file_path(self):
        current_dir = os.path.abspath(os.path.dirname(__file__))
        parent_dir = os.path.abspath(current_dir + f"/../../{self.location}")
        return os.path.join(parent_dir, 'trenitalia.db')

    def search_stops(self, name=None, lat=None, lon=None, limit=4) -> list[Stop]:
        cur = self.con.cursor()
        if lat and lon:
            query = 'SELECT id, name FROM stations WHERE lat NOT NULL AND region_code = 12' \
                    ' ORDER BY ((lat-?)*(lat-?)) + ((lon-?)*(lon-?)) LIMIT ?'
            results = cur.execute(query, (lat, lat, lon, lon, limit)).fetchall()
        else:
            lat, lon = 45.441569, 12.320882
            query = 'SELECT id, name FROM stations WHERE name LIKE ? AND region_code = 12' \
                    ' ORDER BY ((lat-?)*(lat-?)) + ((lon-?)*(lon-?)) LIMIT ?'
            results = cur.execute(query, (f'%{name}%', lat, lat, lon, lon, limit)).fetchall()

        stops = []
        for result in results:
            stops.append(Stop(result[0], result[1]))

        return stops

    def get_stop_from_ref(self, ref) -> Stop:
        cur = self.con.cursor()
        query = 'SELECT name FROM stations WHERE id = ?'
        result = cur.execute(query, (ref,)).fetchone()
        return Stop(ref, result[0], [ref]) if result else None

    def get_stop_times(self, line, start_time, dep_stop_ids, service_ids, LIMIT, day, offset_times) -> list[StopTime]:
        start_dt = datetime.now()
        station_id = dep_stop_ids[0]

        stop_times: list[StopTime] = []

        while len(stop_times) < LIMIT:
            stop_times += self.get_stop_times_from_start_dt(station_id, start_dt)
            stop_times = list({stop_time.trip_id: stop_time for stop_time in stop_times}.values())
            new_start_dt = stop_times[-1].dep_time
            if new_start_dt == start_dt:
                break
            start_dt = new_start_dt

        return stop_times[:LIMIT]

    def get_stop_times_from_start_dt(self, station_id: str, start_dt: datetime) -> list[StopTime]:
        is_dst = start_dt.astimezone().dst() != timedelta(0)
        date = (start_dt - timedelta(hours=(1 if is_dst else 0))).strftime("%a %b %d %Y %H:%M:%S GMT+0100")
        url = f'http://www.viaggiatreno.it/infomobilita/resteasy/viaggiatreno/partenze/{station_id}/{quote(date)}'
        r = requests.get(url)
        if r.status_code != 200:
            return []

        logger.info('URL: %s', url)

        stop_times = []
        for departure in r.json():
            if departure['categoria'] != 'REG':
                continue

            dep_time = datetime.fromtimestamp(departure['orarioPartenza'] / 1000)
            route_name = str(departure['numeroTreno'])
            headsign = departure['destinazione']
            trip_id = departure['numeroTreno']
            stop_sequence = len(departure['compInStazionePartenza']) - 1
            delay = departure['ritardo']

            stop_times.append(StopTime(dep_time, route_name, headsign, trip_id, stop_sequence, delay=delay))

        return stop_times

    def get_stop_times_between_stops(self, dep_stop_ids: set, arr_stop_ids: set, service_ids, line, start_time,
                                     offset_times, limit, day) -> list[StopTime]:
        start_dt = datetime.now()
        is_dst = start_dt.astimezone().dst() != timedelta(0)
        date = (start_dt - timedelta(hours=(1 if is_dst else 0))).strftime("%Y-%m-%dT%H:%M:%S")
        # S02512 to 2512
        dep_station_id = list(dep_stop_ids)[0]
        dep_station_id = int(dep_station_id[1:])
        arr_station_id = list(arr_stop_ids)[0]
        arr_station_id = int(arr_station_id[1:])
        url = f'http://www.viaggiatreno.it/infomobilita/resteasy/viaggiatreno/soluzioniViaggioNew/' \
              f'{dep_station_id}/{arr_station_id}/{quote(date)}'
        print(url)
        r = requests.get(url)
        if r.status_code != 200:
            return []

        stop_times = []

        for solution in r.json()['soluzioni']:
            if len(solution['vehicles']) != 1:
                continue

            vehicle = solution['vehicles'][0]

            if vehicle['categoriaDescrizione'] != 'Regionale' and vehicle['categoriaDescrizione'] != 'RV':
                continue

            dep_time = datetime.strptime(vehicle['orarioPartenza'], '%Y-%m-%dT%H:%M:%S')
            arr_time = datetime.strptime(vehicle['orarioArrivo'], '%Y-%m-%dT%H:%M:%S')

            if day != arr_time.date():
                continue

            route_name = vehicle['numeroTreno']
            headsign = ''
            trip_id = vehicle['numeroTreno']
            stop_sequence = None
            stop_times.append(StopTime(dep_time, route_name, headsign, trip_id, stop_sequence, arr_time))

        return stop_times[:limit]
