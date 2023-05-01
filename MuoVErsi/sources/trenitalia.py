import json
import os
import sqlite3
from sqlite3 import Connection

from MuoVErsi.sources.base import Source, Stop


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
            query = 'SELECT id, name FROM stations WHERE lat NOT NULL ' \
                    'ORDER BY ((lat-?)*(lat-?)) + ((lon-?)*(lon-?)) LIMIT ?'
            results = cur.execute(query, (lat, lat, lon, lon, limit)).fetchall()
        else:
            query = 'SELECT id, name FROM stations WHERE name LIKE ? LIMIT ?'
            results = cur.execute(query, (f'%{name}%', limit)).fetchall()

        stops = []
        for result in results:
            stops.append(Stop(result[0], result[1]))

        return stops

    def get_stop_from_ref(self, ref) -> Stop:
        cur = self.con.cursor()
        query = 'SELECT name FROM stations WHERE id = ?'
        result = cur.execute(query, (ref,)).fetchone()
        return Stop(ref, result[0], [ref]) if result else None
