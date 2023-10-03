import json
import logging
import math
import os
from datetime import datetime, timedelta, date
from urllib.parse import quote

import requests
from sqlalchemy import and_, select
from tqdm import tqdm

from MuoVErsi.sources.base import *

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


class TrenitaliaRoute(Route):
    pass


class Trenitalia(Source):
    LIMIT = 7

    def __init__(self, session, typesense, location='', force_update_stations=False):
        self.location = location
        super().__init__('treni', '🚆', session, typesense)

        if force_update_stations or self.session.query(Station).filter_by(source=self.name).count() == 0 or \
                self.session.query(Stop).filter_by(source=self.name).count() == 0:
            current_dir = os.path.abspath(os.path.dirname(__file__))
            datadir = os.path.abspath(current_dir + '/data')

            with open(os.path.join(datadir, 'trenitalia_stations.json')) as f:
                file_stations = json.load(f)

            new_stations = [
                Station(id=s['code'], name=s['long_name'], lat=s['latitude'], lon=s['longitude'], ids=s['code'],
                        source=self.name, times_count=0) for s
                in
                file_stations]
            self.sync_stations_db(new_stations)

    def save_data(self):
        stations = self.session.scalars(select(Station).filter_by(source=self.name)).all()

        total_times_count = 0
        times_count = []

        tqdm_stations = tqdm(enumerate(stations), total=len(stations))

        for i, station in tqdm_stations:
            tqdm_stations.set_description(f'Processing station {station.name}')
            stop_times = self.get_stop_times_from_station(station)
            total_times_count += len(stop_times)
            times_count.append(len(stop_times))
            self.upload_trip_stop_times_to_postgres(stop_times)

        for i, station in enumerate(stations):
            station.times_count = round(times_count[i] / total_times_count, int(math.log10(total_times_count)) + 1)
        self.sync_stations_db(stations)

    def get_stop_times_from_station(self, station) -> list[TripStopTime]:
        now = datetime.now()
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
        is_dst = start_dt.astimezone().dst() != timedelta(0)
        date = (start_dt - timedelta(hours=(1 if is_dst else 0))).strftime("%a %b %d %Y %H:%M:%S GMT+0100")
        url = f'http://www.viaggiatreno.it/infomobilita/resteasy/viaggiatreno/{type}/{stop.id}/{quote(date)}'
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
                dep_time = datetime.fromtimestamp(departure['orarioPartenza'] / 1000) if departure[
                    'orarioPartenza'] else None
            except ValueError:
                dep_time = None

            if dep_time:
                if dep_time < start_dt - timedelta(minutes=self.MINUTES_TOLERANCE):
                    continue

            try:
                arr_time = datetime.fromtimestamp(departure['orarioArrivo'] / 1000) if departure[
                    'orarioArrivo'] else None
            except ValueError:
                arr_time = None

            if not dep_time and not arr_time:
                continue

            headsign = departure['destinazione']
            stop_sequence = len(departure['compInStazionePartenza']) - 1
            delay = departure['ritardo']

            type_text = 'Partenza' if type == 'partenze' else 'Arrivo'

            platform = departure[f'binarioProgrammato{type_text}Descrizione']

            if departure[f'binarioEffettivo{type_text}Descrizione']:
                if departure[f'binarioEffettivo{type_text}Descrizione'] != '':
                    platform = departure[f'binarioEffettivo{type_text}Descrizione']

            orig_dep_date = datetime.fromtimestamp(departure['dataPartenzaTreno'] / 1000).date() if departure[
                'dataPartenzaTreno'] else None
            origin_id = departure['codOrigine']
            destination = departure.get('destinazione')
            route_name = 'RV' if 3000 <= trip_id < 4000 else 'R'
            stop_time = TripStopTime(stop, origin_id, dep_time, stop_sequence, delay, platform, headsign, trip_id,
                                           route_name,
                                           arr_time=arr_time, orig_dep_date=orig_dep_date, destination=destination)
            stop_times.append(stop_time)

        return stop_times

    def get_stops_from_trip_id(self, trip_id, day: date) -> list[BaseStopTime]:
        query = select(StopTime, Trip, Station) \
            .join(StopTime.train) \
            .join(StopTime.stop) \
            .filter(
            and_(
                Trip.number == trip_id,
                Trip.orig_dep_date == day.isoformat()
            )) \
            .order_by(StopTime.sched_dep_dt)

        results = self.session.execute(query)

        stop_times = []
        for result in results:
            stop_time = TripStopTime(result.Station, result.Trip.orig_id, result.StopTime.sched_dep_dt,
                                           None, 0,
                                           result.StopTime.platform, result.Trip.dest_text, trip_id,
                                           result.Trip.route_name,
                                           result.StopTime.sched_arr_dt, result.Trip.orig_dep_date)
            stop_times.append(stop_time)

        return stop_times
