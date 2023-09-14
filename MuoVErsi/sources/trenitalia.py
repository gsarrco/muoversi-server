import json
import logging
import math
import os
from datetime import datetime, timedelta, time, date
from urllib.parse import quote

import requests
from sqlalchemy import func, and_, select
from sqlalchemy.orm import aliased
from telegram.ext import ContextTypes
from tqdm import tqdm

from MuoVErsi.sources.base import Source, BaseStopTime, Route, Direction, Station, Stop, StopTime, Trip

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


class TrenitaliaStopTime(BaseStopTime):
    def __init__(self, stop: Station, origin_id, dep_time: datetime | None, stop_sequence, delay: int, platform,
                 headsign,
                 trip_id,
                 route_name,
                 arr_time: datetime = None,
                 origin_dep_time: int = None, destination: str = None):
        if arr_time is None:
            arr_time = dep_time
        super().__init__(stop, dep_time, arr_time, stop_sequence, delay, platform, headsign, trip_id, route_name)
        self.origin_dep_time = origin_dep_time
        self.destination = destination
        self.origin_id = origin_id

    def merge(self, arr_stop_time: 'TrenitaliaStopTime'):
        self.arr_time = arr_stop_time.arr_time


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

    def save_trains(self):
        stations = self.session.scalars(select(Station).filter_by(source=self.name)).all()

        total_times_count = 0
        times_count = []

        tqdm_stations = tqdm(enumerate(stations), total=len(stations))

        for i, station in tqdm_stations:
            tqdm_stations.set_description(f'Processing station {station.name}')
            stop_times = self.get_stop_times_from_station(station)
            total_times_count += len(stop_times)
            times_count.append(len(stop_times))
            for stop_time in stop_times:
                train = self.session.query(Trip).filter_by(orig_id=stop_time.origin_id,
                                                            number=stop_time.trip_id,
                                                            orig_dep_date=stop_time.origin_dep_time).first()

                if not train:
                    train = Trip(orig_id=stop_time.origin_id, dest_text=stop_time.destination,
                                  number=stop_time.trip_id, orig_dep_date=stop_time.origin_dep_time,
                                  route_name=stop_time.route_name)
                    self.session.add(train)
                    self.session.commit()

                stop_time_db = self.session.query(StopTime).filter_by(trip_id=train.id, stop_id=station.id).first()

                if stop_time_db:
                    if stop_time_db.platform != stop_time.platform:
                        stop_time_db.platform = stop_time.platform
                        self.session.commit()
                else:
                    new_stop_time = StopTime(trip_id=train.id, stop_id=station.id, sched_arr_dt=stop_time.arr_time,
                                             sched_dep_dt=stop_time.dep_time, platform=stop_time.platform)
                    self.session.add(new_stop_time)
                    self.session.commit()

        for i, station in enumerate(stations):
            station.times_count = round(times_count[i] / total_times_count, int(math.log10(total_times_count)) + 1)
        self.sync_stations_db(stations)

    def get_stop_times_from_station(self, station) -> list[TrenitaliaStopTime]:
        now = datetime.now()
        departures = self.loop_get_times(10000, station, now, type='partenze')
        arrivals = self.loop_get_times(10000, station, now, type='arrivi')

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
                stop_time.destination = station.name.upper()

        return merged

    def file_path(self):
        current_dir = os.path.abspath(os.path.dirname(__file__))
        parent_dir = os.path.abspath(current_dir + f"/../../{self.location}")
        return os.path.join(parent_dir, 'trenitalia.db')

    def get_stop_times(self, stop: Station, line, start_time, day,
                       offset_times, context: ContextTypes.DEFAULT_TYPE | None = None, count=False):
        day_start = datetime.combine(day, time(0))

        if start_time == '':
            start_dt = day_start
        else:
            start_dt = datetime.combine(day, start_time) - timedelta(minutes=self.MINUTES_TOLERANCE)

        end_dt = day_start + timedelta(days=1)

        station_id = stop.ids

        if count:
            raw_stop_times = self.session.query(
                Trip.route_name.label('route_name')
            )
        else:
            raw_stop_times = self.session.query(
                StopTime.sched_arr_dt.label('arr_time'),
                StopTime.sched_dep_dt.label('dep_time'),
                Trip.orig_id.label('origin_id'),
                Trip.dest_text.label('destination'),
                Trip.number.label('trip_id'),
                Trip.orig_dep_date.label('origin_dep_time'),
                StopTime.platform.label('platform'),
                Trip.route_name.label('route_name')
            )

        raw_stop_times = raw_stop_times \
            .select_from(StopTime) \
            .join(Trip, StopTime.trip_id == Trip.id) \
            .filter(
            and_(
                StopTime.stop_id == station_id,
                StopTime.sched_dep_dt >= start_dt,
                StopTime.sched_dep_dt < end_dt
            )
        )

        if line != '':
            raw_stop_times = raw_stop_times.filter(Trip.route_name == line)

        if count:
            raw_stop_times = raw_stop_times \
                .group_by(Trip.route_name) \
                .order_by(func.count(Trip.route_name).desc())
        else:
            raw_stop_times = raw_stop_times.order_by(StopTime.sched_dep_dt).limit(self.LIMIT).offset(offset_times)

        raw_stop_times = raw_stop_times.all()

        if count:
            return [train.route_name for train in raw_stop_times]

        stop_times = []

        for raw_stop_time in raw_stop_times:
            dep_time = raw_stop_time.dep_time
            arr_time = raw_stop_time.arr_time
            stop_time = TrenitaliaStopTime(stop, raw_stop_time.origin_id, dep_time, None, 0, raw_stop_time.platform,
                                           raw_stop_time.destination, raw_stop_time.trip_id,
                                           raw_stop_time.route_name, arr_time=arr_time,
                                           origin_dep_time=raw_stop_time.origin_dep_time)
            stop_times.append(stop_time)

        return stop_times

    def loop_get_times(self, limit, stop: Station, dt, train_ids=None, type='partenze') -> list[TrenitaliaStopTime]:
        results: list[TrenitaliaStopTime] = []

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
            list[TrenitaliaStopTime]:
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

            origin_dep_time = datetime.fromtimestamp(departure['dataPartenzaTreno'] / 1000) if departure[
                'dataPartenzaTreno'] else None
            origin_id = departure['codOrigine']
            destination = departure.get('destinazione')
            route_name = 'RV' if 3000 <= trip_id < 4000 else 'R'
            stop_time = TrenitaliaStopTime(stop, origin_id, dep_time, stop_sequence, delay, platform, headsign, trip_id,
                                           route_name,
                                           arr_time=arr_time, origin_dep_time=origin_dep_time, destination=destination)
            stop_times.append(stop_time)

        return stop_times

    def get_stop_times_between_stops(self, dep_stop: Station, arr_stop: Station, line, start_time,
                                     offset_times, day,
                                     context: ContextTypes.DEFAULT_TYPE | None = None, count=False):
        day_start = datetime.combine(day, time(0))

        if start_time == '':
            start_dt = day_start
        else:
            start_dt = datetime.combine(day, start_time) - timedelta(minutes=self.MINUTES_TOLERANCE)

        end_dt = day_start + timedelta(days=1)

        dep_station_id = dep_stop.ids
        arr_station_id = arr_stop.ids

        # Define alias for stop_times
        a_stop_times = aliased(StopTime)
        d_stop_times = aliased(StopTime)

        if count:
            raw_stop_times = self.session.query(
                Trip.route_name.label('route_name'),
            )
        else:
            raw_stop_times = self.session.query(
                d_stop_times.sched_arr_dt.label('d_arr_time'),
                d_stop_times.sched_dep_dt.label('d_dep_time'),
                Trip.orig_id.label('origin_id'),
                Trip.dest_text.label('destination'),
                Trip.number.label('trip_id'),
                Trip.orig_dep_date.label('origin_dep_time'),
                Trip.route_name.label('route_name'),
                d_stop_times.platform.label('d_platform'),
                a_stop_times.sched_dep_dt.label('a_dep_time'),
                a_stop_times.sched_arr_dt.label('a_arr_time'),
                a_stop_times.platform.label('a_platform')
            )

        raw_stop_times = raw_stop_times \
            .select_from(d_stop_times) \
            .join(a_stop_times, d_stop_times.trip_id == a_stop_times.trip_id) \
            .join(Trip, d_stop_times.trip_id == Trip.id) \
            .filter(
            and_(
                d_stop_times.stop_id == dep_station_id,
                d_stop_times.sched_dep_dt >= start_dt,
                d_stop_times.sched_dep_dt < end_dt,
                d_stop_times.sched_dep_dt < a_stop_times.sched_arr_dt,
                a_stop_times.stop_id == arr_station_id
            )
        )

        if line != '':
            raw_stop_times = raw_stop_times.filter(Trip.route_name == line)

        if count:
            raw_stop_times = raw_stop_times.group_by(Trip.route_name).order_by(func.count(Trip.route_name).desc())
        else:
            raw_stop_times = raw_stop_times.order_by(
                d_stop_times.sched_dep_dt
            ).limit(self.LIMIT).offset(offset_times)

        raw_stop_times = raw_stop_times.all()

        if count:
            return [train.route_name for train in raw_stop_times]

        directions = []

        for raw_stop_time in raw_stop_times:
            d_dep_time = raw_stop_time.d_dep_time
            d_arr_time = raw_stop_time.d_arr_time
            a_dep_time = raw_stop_time.a_dep_time
            a_arr_time = raw_stop_time.a_arr_time
            d_stop_time = TrenitaliaStopTime(
                dep_stop, raw_stop_time.origin_id, d_dep_time, None, 0, raw_stop_time.d_platform,
                raw_stop_time.destination, raw_stop_time.trip_id, raw_stop_time.route_name,
                arr_time=d_arr_time, origin_dep_time=raw_stop_time.origin_dep_time)

            a_stop_time = TrenitaliaStopTime(
                arr_stop, raw_stop_time.origin_id, a_dep_time, None, 0, raw_stop_time.a_platform,
                raw_stop_time.destination, raw_stop_time.trip_id, raw_stop_time.route_name,
                arr_time=a_arr_time, origin_dep_time=raw_stop_time.origin_dep_time)

            route = TrenitaliaRoute(d_stop_time, a_stop_time)
            directions.append(Direction([route]))

        return directions

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
            stop_time = TrenitaliaStopTime(result.Station, result.Trip.orig_id, result.StopTime.sched_dep_dt,
                                           None, 0,
                                           result.StopTime.platform, result.Trip.dest_text, trip_id,
                                           result.Trip.route_name,
                                           result.StopTime.sched_arr_dt, result.Trip.orig_dep_date)
            stop_times.append(stop_time)

        return stop_times
