import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta, time
from sqlite3 import Connection
from urllib.parse import quote

import requests

from MuoVErsi.sources.base import Source, Stop, StopTime, Route, Direction

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


class TrenitaliaRoute(Route):
    def format(self, number, left_time_bold=True, right_time_bold=True):
        line, headsign, trip_id, stop_sequence = self.route_name, self.headsign, \
            self.trip_id, self.dep_stop_time.stop_sequence

        time_format = ""

        if left_time_bold:
            time_format += "<b>"

        time_format += self.dep_stop_time.dt.strftime('%H:%M')

        if self.dep_stop_time.delay > 0:
            time_format += f'+{self.dep_stop_time.delay}m'

        if left_time_bold:
            time_format += "</b>"

        if self.arr_stop_time:
            arr_time = self.arr_stop_time.dt.strftime('%H:%M')

            time_format += "->"

            if right_time_bold:
                time_format += "<b>"

            time_format += arr_time

            if self.arr_stop_time.delay > 0:
                time_format += f'+{self.arr_stop_time.delay}m'

            if right_time_bold:
                time_format += "</b>"

        line = f'{time_format} {headsign}'

        if self.dep_stop_time.platform:
            line += f' bin.{self.dep_stop_time.platform}'

        if self.dep_stop_time.dt < datetime.now():
            line = f'<del>{line}</del>'

        if number:
            return f'\n{number}. {line}'
        else:
            return f'\n⎿ {line}'

class Trenitalia(Source):
    def __init__(self, location=''):
        self.location = location
        super().__init__('treni', False)

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

        with open(os.path.join(datadir, 'trenitalia_stations.json')) as f:
            stations = json.load(f)

        for station in stations:
            _id = station.get('code', None)
            name = station.get('long_name', None)
            region_code = station.get('region', None)
            lat = station.get('latitude', None)
            lon = station.get('longitude', None)

            # insert values into stations table
            cur.execute("""
                INSERT INTO stations (id, name, region_code, lat, lon)
                VALUES (?, ?, ?, ?, ?)
                """,
                (_id, name, region_code, lat, lon)
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

    def get_stop_times(self, line, start_time, dep_stop_ids, service_ids, LIMIT, day, offset_times)\
            -> list[TrenitaliaRoute]:
        if start_time == '':
            start_dt = datetime.combine(day, time(5))
        else:
            start_dt = datetime.combine(day, start_time) - timedelta(minutes=5)

        dt = start_dt
        station_id = dep_stop_ids[0]

        return self.loop_get_times(LIMIT, station_id, dt)

    def loop_get_times(self, limit, station_id, dt, train_ids=None) -> list[TrenitaliaRoute]:
        routes: list[TrenitaliaRoute] = []

        notimes = 0

        while len(routes) < limit:
            routes += self.get_stop_times_from_start_dt(station_id, dt, train_ids)
            routes = list({route.trip_id: route for route in routes}.values())
            if len(routes) == 0:
                dt = dt + timedelta(hours=1)
                notimes += 1
                if notimes > 4:
                    break
                continue
            new_start_dt = routes[-1].dep_stop_time.dt
            if new_start_dt == dt:
                break
            dt = new_start_dt

        return routes[:limit]

    def get_stop_times_from_start_dt(self, station_id: str, start_dt: datetime, train_ids: list[int] | None) -> list[TrenitaliaRoute]:
        is_dst = start_dt.astimezone().dst() != timedelta(0)
        date = (start_dt - timedelta(hours=(1 if is_dst else 0))).strftime("%a %b %d %Y %H:%M:%S GMT+0100")
        url = f'http://www.viaggiatreno.it/infomobilita/resteasy/viaggiatreno/partenze/{station_id}/{quote(date)}'
        r = requests.get(url)
        if r.status_code != 200:
            return []

        logger.info('URL: %s', url)

        routes = []
        for departure in r.json():
            if departure['categoria'] != 'REG':
                continue

            trip_id: int = departure['numeroTreno']

            if train_ids:
                if trip_id not in train_ids:
                    continue

            dep_time = datetime.fromtimestamp(departure['orarioPartenza'] / 1000)

            if dep_time < start_dt - timedelta(minutes=5):
                continue

            if 3000 <= trip_id < 4000:
                acronym = 'RV'
            else:
                acronym = 'R'

            route_name = acronym + str(departure['numeroTreno'])
            headsign = departure['destinazione']
            stop_sequence = len(departure['compInStazionePartenza']) - 1
            delay = departure['ritardo']

            if departure['binarioEffettivoPartenzaDescrizione']:
                platform = departure['binarioEffettivoPartenzaDescrizione']
            else:
                platform = departure['binarioProgrammatoPartenzaDescrizione']

            dep_stop_time = StopTime(dep_time, 0, delay, platform)
            route = TrenitaliaRoute(dep_stop_time, None, route_name, headsign, trip_id)
            routes.append(route)

        return routes

    def get_stop_times_between_stops(self, dep_stop_ids: set, arr_stop_ids: set, service_ids, line, start_time,
                                     offset_times, limit, day) -> list[Direction]:
        if start_time == '':
            date = datetime.combine(day, time(5))
        else:
            date = datetime.combine(day, start_time) - timedelta(minutes=5)

        # S02512 to 2512
        dep_station_id_raw = list(dep_stop_ids)[0]
        dep_station_id = int('8300' + dep_station_id_raw[1:])
        arr_station_id_raw = list(arr_stop_ids)[0]
        arr_station_id = int('8300' + arr_station_id_raw[1:])
        url = 'https://www.lefrecce.it/Channels.Website.BFF.WEB/website/ticket/solutions'
        r = requests.post(url, json={
            "departureLocationId": dep_station_id,
            "arrivalLocationId": arr_station_id,
            "departureTime": date.isoformat(),
            "adults": 1,
            "children": 0,
            "criteria": {
                "frecceOnly": False,
                "regionalOnly": True,
                "noChanges": False,
                "order": "DEPARTURE_DATE",
                "limit": 5,
                "offset": offset_times
            },
            "advancedSearchRequest": {
                "bestFare": False
            }
        })

        if r.status_code != 200:
            return []

        resp = r.json()

        data = {}
        for solution_index, solution in enumerate(resp['solutions']):
            for train in solution['solution']['nodes']:
                station_name = train['origin']
                train_id = int(train['train']['name'])
                dep_time = datetime.strptime(train['departureTime'], '%Y-%m-%dT%H:%M:%S.%f%z').replace(
                    tzinfo=None)
                arr_time = datetime.strptime(train['arrivalTime'], '%Y-%m-%dT%H:%M:%S.%f%z').replace(
                    tzinfo=None)
                data.setdefault(station_name, []).append((train_id, dep_time, arr_time, solution_index))

        solutions = {}

        for station_name, trains in data.items():
            r = requests.get('https://www.lefrecce.it/Channels.Website.BFF.WEB/website/locations/search', params={
                'name': station_name,
                'limit': 1
            })

            logger.info('URL: %s', r.url)

            station_id = 'S' + str(r.json()[0]['id'])[4:]

            train_ids = [train[0] for train in trains]
            first_train_dep_time = trains[0][1]
            routes = self.loop_get_times(10, station_id, first_train_dep_time, train_ids)

            for train, route in zip(trains, routes):
                route.arr_stop_time = StopTime(train[2], 0, 0, None)
                solutions.setdefault(train[3], []).append(route)

        solutions = dict(sorted(solutions.items()))
        directions = [Direction(routes) for routes in solutions.values()]

        return directions

    def get_andamento_treno(self, train_id, dep_station_id, arr_station_id) -> tuple[int, int]:
        url = f'http://www.viaggiatreno.it/infomobilita/resteasy/viaggiatreno/cercaNumeroTrenoTrenoAutocomplete/' \
              f'{train_id}'
        r = requests.get(url)

        if r.status_code != 200:
            return 0, 0

        logger.info('URL: %s', url)

        response = r.text

        if response == '':
            return 0, 0

        train_id, origin_id, dep_time = response.split('|')[1].rstrip().split('-')

        url = f'http://www.viaggiatreno.it/infomobilita/resteasy/viaggiatreno/andamentoTreno/' \
              f'{origin_id}/{train_id}/{dep_time}'

        r = requests.get(url)
        if r.status_code != 200:
            return 0, 0

        logger.info('URL: %s', url)

        response = r.json()

        dep_delay = 0
        arr_delay = 0

        for stop in response['fermate']:
            if stop['id'] == dep_station_id:
                dep_delay = stop['ritardo']
                continue

            if stop['id'] == arr_station_id:
                arr_delay = stop['ritardo']
                continue

        return dep_delay, arr_delay
