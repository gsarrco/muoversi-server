import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta, time
from sqlite3 import Connection
from time import sleep
from urllib.parse import quote

import requests
from tqdm import tqdm

from MuoVErsi.sources.base import Source, Stop, StopTime, Route, Direction

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


class TrenitaliaStopTime(StopTime):
    def __init__(self, origin_id, dep_time: datetime | None, stop_sequence, delay: int, platform, headsign, trip_id, route_name,
                 stop_name: str = None,
                 arr_time: datetime = None,
                 origin_dep_time: int = None, destination: str = None):
        if arr_time is None:
            arr_time = dep_time
        super().__init__(dep_time, arr_time, stop_sequence, delay, platform, headsign, trip_id, route_name, stop_name)
        self.origin_dep_time = origin_dep_time
        self.destination = destination
        self.origin_id = origin_id

    def merge(self, arr_stop_time: 'TrenitaliaStopTime'):
        self.arr_time = arr_stop_time.arr_time

    def format(self, number, left_time_bold=True, right_time_bold=True):
        line, headsign, trip_id, stop_sequence = self.route_name, self.headsign, \
            self.trip_id, self.stop_sequence

        time_format = ""

        if left_time_bold:
            time_format += "<b>"

        time_format += self.dep_time.strftime('%H:%M')

        if self.delay > 0:
            time_format += f'+{self.delay}m'

        if left_time_bold:
            time_format += "</b>"

        platform = self.platform if self.platform else '/'
        line = f'{time_format} {headsign}\n⎿ <i>{line} BIN. {platform}</i>'

        if self.dep_time < datetime.now():
            line = f'<del>{line}</del>'

        if number:
            return f'\n{number}. {line}'
        else:
            return f'\n⎿ {line}'


class TrenitaliaRoute(Route):
    def format(self, number, left_time_bold=True, right_time_bold=True):
        line, headsign, trip_id, stop_sequence = self.dep_stop_time.route_name, self.dep_stop_time.headsign, \
            self.dep_stop_time.trip_id, self.dep_stop_time.stop_sequence

        time_format = ""

        if left_time_bold:
            time_format += "<b>"

        time_format += self.dep_stop_time.dep_time.strftime('%H:%M')

        if self.dep_stop_time.delay > 0:
            time_format += f'+{self.dep_stop_time.delay}m'

        if left_time_bold:
            time_format += "</b>"

        if self.arr_stop_time:
            arr_time = self.arr_stop_time.arr_time.strftime('%H:%M')

            time_format += "->"

            if right_time_bold:
                time_format += "<b>"

            time_format += arr_time

            if self.arr_stop_time.delay > 0:
                time_format += f'+{self.arr_stop_time.delay}m'

            if right_time_bold:
                time_format += "</b>"

        dep_platform = self.dep_stop_time.platform if self.dep_stop_time.platform else '/'
        arr_platform = self.arr_stop_time.platform if self.arr_stop_time.platform else '/'
        headsign = headsign[:17]
        line = f'{time_format} {headsign}\n⎿ <i>{line} BIN. {dep_platform} -> {arr_platform}</i>'

        if self.dep_stop_time.dep_time < datetime.now():
            line = f'<del>{line}</del>'

        if number:
            return f'\n{number}. {line}'
        else:
            return f'\n⎿ {line}'


class Trenitalia(Source):
    LIMIT = 7

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

    def save_trains(self):
        cur = self.con.cursor()

        # create table "trains" in database if not exists
        cur.execute("""
            CREATE TABLE IF NOT EXISTS trains (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codOrigine TEXT,
                destinazione TEXT,
                numeroTreno INTEGER,
                dataPartenzaTreno INTEGER,
                statoTreno TEXT DEFAULT 'regol.',
                FOREIGN KEY (codOrigine) REFERENCES stations(id),
                UNIQUE(codOrigine, numeroTreno, dataPartenzaTreno)
            )
            """
        )

        cur.execute("""
            CREATE TABLE IF NOT EXISTS stop_times (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                train_id INTEGER,
                idFermata TEXT,
                arrivo_teorico TEXT,
                arrivo_reale TEXT,
                partenza_teorica TEXT,
                partenza_reale TEXT,
                ritardo_arrivo TEXT,
                ritardo_partenza TEXT,
                binario TEXT,
                UNIQUE(train_id, idFermata),
                FOREIGN KEY(train_id) REFERENCES trains(id),
                FOREIGN KEY(idFermata) REFERENCES stations(id)
            )
            """
        )

        query = 'SELECT id, name FROM stations WHERE region_code = 12'
        stations = cur.execute(query).fetchall()

        pbar = tqdm(stations)
        for station in pbar:
            pbar.set_description("Processing %s" % station[1])
            stop_times = self.get_stop_times_from_station(station)
            for stop_time in stop_times:
                cur = self.con.cursor()
                # insert or select train
                cur.execute('SELECT id FROM trains WHERE codOrigine = ? AND numeroTreno = ? AND dataPartenzaTreno = ?',
                            (stop_time.origin_id, stop_time.trip_id, stop_time.origin_dep_time)
                            )
                train_id = cur.fetchone()

                if train_id:
                    train_id = train_id[0]
                else:
                    cur.execute('INSERT OR IGNORE INTO trains (codOrigine, destinazione, numeroTreno, dataPartenzaTreno) '
                                'VALUES (?, ?, ?, ?)',
                                (stop_time.origin_id, stop_time.destination, stop_time.trip_id, stop_time.origin_dep_time)
                                )
                    train_id = cur.lastrowid

                # select stop_time if exists
                db_stop_time = cur.execute('SELECT id FROM stop_times WHERE train_id = ? AND idFermata = ?',
                            (train_id, station[0])
                            ).fetchone()

                if db_stop_time:
                    cur.execute('UPDATE stop_times SET binario = ? WHERE id = ?',
                                (stop_time.platform, db_stop_time[0]))
                else:
                    cur.execute(
                        'INSERT OR IGNORE INTO stop_times (train_id, idFermata, arrivo_teorico, partenza_teorica, binario) '
                        'VALUES (?, ?, ?, ?, ?)',
                        (train_id, station[0], stop_time.arr_time, stop_time.dep_time, stop_time.platform)
                        )

                self.con.commit()

    def get_stop_times_from_station(self, station) -> list[TrenitaliaStopTime]:
        now = datetime.now()
        departures = self.loop_get_times(10000, station[0], now, type='partenze')
        arrivals = self.loop_get_times(10000, station[0], now, type='arrivi')

        departures_arrivals = departures + arrivals

        # merge departures and arrivals StopTime when they have the same trip_id and origin_dep_time
        departures_arrivals.sort(key=lambda x: (x.trip_id, x.origin_dep_time))
        merged = []
        for i, stop_time in enumerate(departures_arrivals):
            if i == 0:
                merged.append(stop_time)
            else:
                if stop_time.trip_id == merged[-1].trip_id and stop_time.origin_dep_time == merged[-1].origin_dep_time:
                    if stop_time.dep_time:
                        stop_time.merge(merged[-1])
                    else:
                        merged[-1].merge(stop_time)
                else:
                    merged.append(stop_time)

        for stop_time in merged:
            if not stop_time.destination:
                stop_time.destination = station[1].upper()

        return merged


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

    def get_stop_from_ref(self, ref) -> Stop | None:
        cur = self.con.cursor()
        query = 'SELECT name FROM stations WHERE id = ?'
        result = cur.execute(query, (ref,)).fetchone()
        return Stop(ref, result[0], [ref]) if result else None

    def get_stop_times(self, line, start_time, dep_stop_ids, service_ids, day, offset_times)\
            -> list[TrenitaliaStopTime]:
        if start_time == '':
            start_dt = datetime.combine(day, time(4))
        else:
            start_dt = datetime.combine(day, start_time) - timedelta(minutes=5)

        end_dt = datetime.combine(day + timedelta(days=1), time(4))

        dt = start_dt
        station_id = dep_stop_ids[0]

        # get stop_times from db
        cur = self.con.cursor()
        cur.row_factory = sqlite3.Row
        raw_stop_times = cur.execute("""
            SELECT
                s.arrivo_teorico as arr_time,
                s.partenza_teorica as dep_time,
                t.codOrigine as origin_id,
                t.destinazione as destination,
                t.numeroTreno as trip_id,
                t.dataPartenzaTreno as origin_dep_time,
                s.binario as platform
            FROM stop_times s
            INNER JOIN trains t ON s.train_id = t.id
            WHERE s.idFermata = ? AND s.partenza_teorica BETWEEN ? AND ?
            ORDER BY s.partenza_teorica
            LIMIT ? OFFSET ?
            """, (station_id, start_dt, end_dt, self.LIMIT, offset_times)).fetchall()

        stop_times = []

        for raw_stop_time in raw_stop_times:
            dep_time = datetime.strptime(raw_stop_time['dep_time'], '%Y-%m-%d %H:%M:%S')
            arr_time = datetime.strptime(raw_stop_time['arr_time'], '%Y-%m-%d %H:%M:%S')
            stop_time = TrenitaliaStopTime(raw_stop_time['origin_id'], dep_time, None, 0, raw_stop_time['platform'],
                                           raw_stop_time['destination'], raw_stop_time['trip_id'],
                                           raw_stop_time['trip_id'], arr_time=arr_time,
                                           origin_dep_time=raw_stop_time['origin_dep_time'])
            stop_times.append(stop_time)

        return stop_times

    def loop_get_times(self, limit, station_id, dt, train_ids=None, type='partenze') -> list[TrenitaliaStopTime]:
        results: list[TrenitaliaStopTime] = []

        notimes = 0

        while len(results) < limit:
            stop_times = self.get_stop_times_from_start_dt(type, station_id, dt, train_ids)
            if len(stop_times) == 0:
                dt = dt + timedelta(hours=1)
                if notimes > 7:
                    break
                notimes += 1
                continue

            for result in results:
                # remove stop_times with the same trip_id and dep_time/arr_time
                if type == 'partenze':
                    stop_times = [x for x in stop_times if (x.trip_id, x.dep_time) != (result.trip_id, result.dep_time)]
                else:
                    stop_times = [x for x in stop_times if (x.trip_id, x.arr_time) != (result.trip_id, result.arr_time)]

            results.extend(stop_times)

            if type == 'partenze':
                new_start_dt = results[-1].dep_time
            else:
                new_start_dt = results[-1].arr_time
            if new_start_dt == dt:
                dt = dt + timedelta(hours=1)
            else:
                dt = new_start_dt
            notimes = 0

        return results[:limit]

    def get_stop_times_from_start_dt(self, type, station_id: str, start_dt: datetime, train_ids: list[int] | None) -> list[TrenitaliaStopTime]:
        is_dst = start_dt.astimezone().dst() != timedelta(0)
        date = (start_dt - timedelta(hours=(1 if is_dst else 0))).strftime("%a %b %d %Y %H:%M:%S GMT+0100")
        url = f'http://www.viaggiatreno.it/infomobilita/resteasy/viaggiatreno/{type}/{station_id}/{quote(date)}'
        r = requests.get(url)
        if r.status_code != 200:
            return []

        stop_times = []
        for departure in r.json():
            if departure['categoria'] != 'REG':
                continue

            trip_id: int = departure['numeroTreno']

            if train_ids:
                if trip_id not in train_ids:
                    continue

            try:
                dep_time = datetime.fromtimestamp(departure['orarioPartenza'] / 1000) if departure['orarioPartenza'] else None
            except ValueError:
                dep_time = None

            if dep_time:
                if dep_time < start_dt - timedelta(minutes=5):
                    continue

            try:
                arr_time = datetime.fromtimestamp(departure['orarioArrivo'] / 1000) if departure['orarioArrivo'] else None
            except ValueError:
                arr_time = None

            if not dep_time and not arr_time:
                continue

            if 3000 <= trip_id < 4000:
                acronym = 'RV'
            else:
                acronym = 'R'

            route_name = acronym + str(departure['numeroTreno'])
            headsign = departure['destinazione']
            stop_sequence = len(departure['compInStazionePartenza']) - 1
            delay = departure['ritardo']

            type_text = 'Partenza' if type == 'partenze' else 'Arrivo'

            platform = departure[f'binarioProgrammato{type_text}Descrizione']

            if departure[f'binarioEffettivo{type_text}Descrizione']:
                if departure[f'binarioEffettivo{type_text}Descrizione'] != '':
                    platform = departure[f'binarioEffettivo{type_text}Descrizione']

            origin_dep_time = departure['dataPartenzaTreno']
            origin_id = departure['codOrigine']
            destination = departure.get('destinazione')

            stop_time = TrenitaliaStopTime(origin_id, dep_time, stop_sequence, delay, platform, headsign, trip_id, route_name,
                                           arr_time=arr_time, origin_dep_time=origin_dep_time, destination=destination)
            stop_times.append(stop_time)

        sleep(1)

        return stop_times

    def get_stop_times_between_stops(self, dep_stop_ids: set, arr_stop_ids: set, service_ids, line, start_time,
                                     offset_times, day) -> list[Direction]:
        if start_time == '':
            start_dt = datetime.combine(day, time(4))
        else:
            start_dt = datetime.combine(day, start_time) - timedelta(minutes=5)

        end_dt = datetime.combine(day + timedelta(days=1), time(4))

        dep_station_id = next(iter(dep_stop_ids))
        arr_station_id = next(iter(arr_stop_ids))

        cur = self.con.cursor()
        cur.row_factory = sqlite3.Row
        raw_stop_times = cur.execute("""
                    SELECT
                        d.arrivo_teorico as d_arr_time,
                        d.partenza_teorica as d_dep_time,
                        t.codOrigine as origin_id,
                        t.destinazione as destination,
                        t.numeroTreno as trip_id,
                        t.dataPartenzaTreno as origin_dep_time,
                        d.binario as d_platform,
                        a.partenza_teorica as a_dep_time,
                        a.arrivo_teorico as a_arr_time,
                        a.binario as a_platform
                    FROM stop_times d
                        INNER JOIN (
                            SELECT
                                train_id,
                                arrivo_teorico,
                                partenza_teorica,
                                binario
                            FROM stop_times
                            WHERE stop_times.idFermata = ?
                            ORDER BY stop_times.arrivo_teorico
                        ) a ON d.train_id = a.train_id
                        INNER JOIN trains t ON d.train_id = t.id
                    WHERE d.idFermata = ? AND d.partenza_teorica BETWEEN ? AND ?
                        AND d_dep_time < a_arr_time
                    ORDER BY d.partenza_teorica
                    LIMIT ? OFFSET ?
                    """, (arr_station_id, dep_station_id, start_dt, end_dt, self.LIMIT, offset_times)).fetchall()

        directions = []

        for raw_stop_time in raw_stop_times:
            d_dep_time = datetime.strptime(raw_stop_time['d_dep_time'], '%Y-%m-%d %H:%M:%S')
            d_arr_time = datetime.strptime(raw_stop_time['d_arr_time'], '%Y-%m-%d %H:%M:%S') if raw_stop_time['d_arr_time'] else None
            a_dep_time = datetime.strptime(raw_stop_time['a_dep_time'], '%Y-%m-%d %H:%M:%S') if raw_stop_time['a_dep_time'] else None
            a_arr_time = datetime.strptime(raw_stop_time['a_arr_time'], '%Y-%m-%d %H:%M:%S')
            d_stop_time = TrenitaliaStopTime(raw_stop_time['origin_id'], d_dep_time, None, 0, raw_stop_time['d_platform'],
                                           raw_stop_time['destination'], raw_stop_time['trip_id'],
                                           raw_stop_time['trip_id'], arr_time=d_arr_time,
                                           origin_dep_time=raw_stop_time['origin_dep_time'])
            a_stop_time = TrenitaliaStopTime(raw_stop_time['origin_id'], a_dep_time, None, 0, raw_stop_time['a_platform'],
                                             raw_stop_time['destination'], raw_stop_time['trip_id'],
                                             raw_stop_time['trip_id'], arr_time=a_arr_time,
                                             origin_dep_time=raw_stop_time['origin_dep_time'])
            route = TrenitaliaRoute(d_stop_time, a_stop_time)
            directions.append(Direction([route]))

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
