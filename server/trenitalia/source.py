import json
import math
import os

import requests
from zoneinfo import ZoneInfo
from tqdm import tqdm

from server.base import *

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

rome_tz = ZoneInfo('Europe/Berlin')


class Trenitalia(Source):
    LIMIT = 7

    def __init__(self, session, typesense, location='', force_update_stations=False):
        self.location = location
        super().__init__('venezia-treni', '🚆', session, typesense)

        if force_update_stations or self.session.query(Station).filter_by(source=self.name, active=True).count() == 0 or \
                self.session.query(Stop).filter_by(source=self.name, active=True).count() == 0:
            current_dir = os.path.abspath(os.path.dirname(__file__))
            parent_dir = os.path.abspath(os.path.join(current_dir, os.pardir))
            datadir = os.path.abspath(parent_dir + '/data')

            with open(os.path.join(datadir, 'trenitalia_stations.json')) as f:
                file_stations = json.load(f)

            new_stations = [
                Station(id=s['code'], name=s['long_name'], lat=s['latitude'], lon=s['longitude'], ids=s['code'],
                        source=self.name, times_count=0) for s
                in
                file_stations]
            self.sync_stations_db(new_stations)

    def save_data(self):
        stations = self.session.scalars(
            select(Station)
                .filter_by(source=self.name, active=True)
                .order_by(Station.times_count.desc(), Station.name.asc())
        ).all()

        max_times_count = 0
        times_count = []

        tqdm_stations = tqdm(enumerate(stations), total=len(stations), desc=f'Uploading {self.name} data')

        for i, station in tqdm_stations:
            tqdm_stations.set_description(f'Processing station {station.name}')
            stop_times = self.get_stop_times_from_station(station)
            stop_times_count = len(stop_times)
            if stop_times_count > max_times_count:
                max_times_count = stop_times_count
            times_count.append(stop_times_count)
            for stop_time in stop_times:
                self.upload_trip_stop_time_to_postgres(stop_time)

        for i, station in enumerate(stations):
            station.times_count = round(times_count[i] / max_times_count, int(math.log10(max_times_count)) + 1)
        self.sync_stations_db(stations)

    def get_stop_times_from_station(self, station) -> list[TripStopTime]:
        now = datetime.now(rome_tz)
        departures = self.loop_get_times(10000, station, now, type='partenze')
        arrivals = self.loop_get_times(10000, station, now, type='arrivi')

        departures_arrivals = departures + arrivals

        # merge departures and arrivals StopTime when they have the same trip_id and orig_dep_date
        departures_arrivals.sort(key=lambda x: (x.trip_id, x.orig_dep_date))
        merged = []
        for i, stop_time in enumerate(departures_arrivals):
            if i == 0:
                merged.append(stop_time)
            else:
                if stop_time.trip_id == merged[-1].trip_id and stop_time.orig_dep_date == merged[-1].orig_dep_date:
                    if stop_time.dep_time:
                        stop_time.merge(merged[-1])
                    else:
                        merged[-1].merge(stop_time)
                else:
                    merged.append(stop_time)

        for stop_time in merged:
            if not stop_time.destination:
                stop_time.destination = station.name.upper()

        return merged

    def file_path(self):
        current_dir = os.path.abspath(os.path.dirname(__file__))
        parent_dir = os.path.abspath(current_dir + f"/../../{self.location}")
        return os.path.join(parent_dir, 'trenitalia.db')

    def loop_get_times(self, limit, stop: Station, dt, train_ids=None, type='partenze') -> list[TripStopTime]:
        results: list[TripStopTime] = []

        notimes = 0

        while len(results) < limit:
            stop_times = self.get_stop_times_from_start_dt(type, stop, dt, train_ids)
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

            if new_start_dt <= dt:
                dt = dt + timedelta(hours=1)
            else:
                dt = new_start_dt
            notimes = 0

        return results[:limit]

    def get_stop_times_from_start_dt(self, type, stop: Station, start_dt: datetime, train_ids: list[int] | None) -> \
            list[TripStopTime]:
        num_offset = start_dt.strftime('%z')
        sc_num_offset = f'{num_offset[:3]}:{num_offset[3:]}'
        url_dt = start_dt.strftime('%a %b %d %Y %H:%M:%S GMT') + f'{num_offset} (GMT{sc_num_offset})'
        url_dt = url_dt.replace(' ', '%20')
        url = f'http://www.viaggiatreno.it/infomobilita/resteasy/viaggiatreno/{type}/{stop.id}/{url_dt}'
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
                dep_time = datetime.fromtimestamp(departure['orarioPartenza'] / 1000, tz=rome_tz) if departure[
                    'orarioPartenza'] else None
            except ValueError:
                dep_time = None

            if dep_time:
                if dep_time < start_dt - timedelta(minutes=self.MINUTES_TOLERANCE):
                    continue

            try:
                arr_time = datetime.fromtimestamp(departure['orarioArrivo'] / 1000, tz=rome_tz) if departure[
                    'orarioArrivo'] else None
            except ValueError:
                arr_time = None

            if not dep_time and not arr_time:
                continue

            headsign = departure['destinazione']
            delay = departure['ritardo']

            type_text = 'Partenza' if type == 'partenze' else 'Arrivo'

            platform = departure[f'binarioProgrammato{type_text}Descrizione']

            if departure[f'binarioEffettivo{type_text}Descrizione']:
                if departure[f'binarioEffettivo{type_text}Descrizione'] != '':
                    platform = departure[f'binarioEffettivo{type_text}Descrizione']

            orig_dep_date = datetime.fromtimestamp(departure['dataPartenzaTreno'] / 1000, tz=rome_tz).date() if departure[
                'dataPartenzaTreno'] else None
            origin_id = departure['codOrigine']
            destination = departure.get('destinazione')
            route_name = 'RV' if 3000 <= trip_id < 4000 else 'R'
            stop_time = TripStopTime(stop, origin_id, dep_time, None, delay, platform, headsign, trip_id,
                                           route_name,
                                           arr_time=arr_time, orig_dep_date=orig_dep_date, destination=destination)
            stop_times.append(stop_time)

        return stop_times
