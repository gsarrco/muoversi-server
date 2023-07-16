import json
import logging
import os
from datetime import datetime, timedelta, time, date
from typing import Optional
from urllib.parse import quote

import requests
import yaml
from sqlalchemy import create_engine, String, UniqueConstraint, ForeignKey, func, and_
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker, relationship, aliased, Mapped, mapped_column, declarative_base
from telegram.ext import ContextTypes

from MuoVErsi.sources.base import Source, Stop, StopTime as BaseStopTime, Route, Direction

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
config_path = os.path.join(base_dir, 'config.yaml')
with open(config_path, 'r') as config_file:
    try:
        config = yaml.safe_load(config_file)
        logger.info(config)
    except yaml.YAMLError as err:
        logger.error(err)

engine_url = f"postgresql://{config['PGUSER']}:{config['PGPASSWORD']}@{config['PGHOST']}:{config['PGPORT']}/" \
             f"{config['PGDATABASE']}"
engine = create_engine(engine_url, echo=config['DEV'])


class TrenitaliaStopTime(BaseStopTime):
    def __init__(self, stop: Stop, origin_id, dep_time: datetime | None, stop_sequence, delay: int, platform, headsign,
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


Base = declarative_base()


class Station(Base):
    __tablename__ = 'stations'

    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    region_code: Mapped[int]
    lat: Mapped[float]
    lon: Mapped[float]


class Train(Base):
    __tablename__ = 'trains'

    id: Mapped[int] = mapped_column(primary_key=True)
    codOrigine: Mapped[str] = mapped_column(ForeignKey('stations.id'))
    destinazione: Mapped[str]
    numeroTreno: Mapped[int]
    dataPartenzaTreno: Mapped[date]
    statoTreno: Mapped[str] = mapped_column(String, default='regol.')
    categoria: Mapped[str]

    __table_args__ = (UniqueConstraint('codOrigine', 'numeroTreno', 'dataPartenzaTreno'),)


class StopTime(Base):
    __tablename__ = 'stop_times'

    id: Mapped[int] = mapped_column(primary_key=True)
    train_id: Mapped[int] = mapped_column(ForeignKey('trains.id'))
    train: Mapped[Train] = relationship('Train', backref='stop_times')
    idFermata: Mapped[str] = mapped_column(ForeignKey('stations.id'))
    station: Mapped[Station] = relationship('Station', backref='stop_times')
    arrivo_teorico: Mapped[datetime]
    arrivo_reale: Mapped[datetime]
    partenza_teorica: Mapped[datetime]
    partenza_reale: Mapped[datetime]
    ritardo_arrivo: Mapped[int]
    ritardo_partenza: Mapped[int]
    binario: Mapped[str]

    __table_args__ = (UniqueConstraint('train_id', 'idFermata'),)


class Trenitalia(Source):
    LIMIT = 7

    def __init__(self, location=''):
        self.location = location
        super().__init__('treni')

        Base.metadata.create_all(engine)

        self.Session = sessionmaker(bind=engine)
        self.session = self.Session()

        self.populate_db()

    def populate_db(self):
        if self.session.query(Station).count() != 0:
            return

        current_dir = os.path.abspath(os.path.dirname(__file__))
        datadir = os.path.abspath(current_dir + '/data')

        with open(os.path.join(datadir, 'trenitalia_stations.json')) as f:
            stations = json.load(f)

        for station in stations:
            _id = station.get('code', None)
            name = station.get('long_name', None)
            region_code = station.get('region', None)

            # if lat and long are empty strings, set them to None
            lat = station.get('latitude', None)
            lon = station.get('longitude', None)

            if lat == '':
                lat = None
            if lon == '':
                lon = None

            station = Station(id=_id, name=name, region_code=region_code, lat=lat, lon=lon)
            self.session.add(station)

        self.session.commit()

    def save_trains(self):
        stations = self.session.query(Station).filter(Station.region_code == 12).all()

        for i, station in enumerate(stations):
            stop_times = self.get_stop_times_from_station(station)
            for stop_time in stop_times:
                train = self.session.query(Train).filter_by(codOrigine=stop_time.origin_id,
                                                            numeroTreno=stop_time.trip_id,
                                                            dataPartenzaTreno=stop_time.origin_dep_time).first()

                if not train:
                    train = Train(codOrigine=stop_time.origin_id, destinazione=stop_time.destination,
                                  numeroTreno=stop_time.trip_id, dataPartenzaTreno=stop_time.origin_dep_time,
                                  categoria=stop_time.route_name)
                    self.session.add(train)
                    self.session.commit()

                stop_time_db = self.session.query(StopTime).filter_by(train_id=train.id, idFermata=station.id).first()

                if stop_time_db:
                    if stop_time_db.binario != stop_time.platform:
                        stop_time_db.binario = stop_time.platform
                        self.session.commit()
                else:
                    new_stop_time = StopTime(train_id=train.id, idFermata=station.id, arrivo_teorico=stop_time.arr_time,
                                             partenza_teorica=stop_time.dep_time, binario=stop_time.platform)
                    self.session.add(new_stop_time)
                    self.session.commit()
            logger.info(f'{i + 1}/{len(stations)}: saved station {station.name}, stop_times: {len(stop_times)}')

    def get_stop_times_from_station(self, station) -> list[TrenitaliaStopTime]:
        now = datetime.now()
        stop = Stop(station.id, station.name, [station.id])
        departures = self.loop_get_times(10000, stop, now, type='partenze')
        arrivals = self.loop_get_times(10000, stop, now, type='arrivi')

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

    def search_stops(self, name=None, lat=None, lon=None, limit=4):
        if lat and lon:
            results = self.session.query(Station.id, Station.name).filter(Station.lat.isnot(None),
                                                                          Station.region_code == 12).order_by(
                func.abs(Station.lat - lat) + func.abs(Station.lon - lon)).limit(limit).all()
        else:
            lat, lon = 45.441569, 12.320882
            results = self.session.query(Station.id, Station.name).filter(Station.name.ilike(f'%{name}%'),
                                                                          Station.region_code == 12).order_by(
                func.abs(Station.lat - lat) + func.abs(Station.lon - lon)).limit(limit).all()

        stops = []
        for result in results:
            stops.append(Stop(result.id, result.name))

        return stops

    def get_stop_from_ref(self, ref):
        result = self.session.query(Station.name).filter(Station.id == ref).first()
        return Stop(ref, result.name, [ref]) if result else None

    def get_stop_times(self, stop: Stop, line, start_time, day,
                       offset_times, context: ContextTypes.DEFAULT_TYPE | None = None, count=False):
        day_start = datetime.combine(day, time(0))

        if start_time == '':
            start_dt = day_start
        else:
            start_dt = datetime.combine(day, start_time) - timedelta(minutes=self.MINUTES_TOLERANCE)

        end_dt = day_start + timedelta(days=1)

        station_id = stop.ids[0]

        if count:
            raw_stop_times = self.session.query(
                Train.categoria.label('route_name')
            )
        else:
            raw_stop_times = self.session.query(
                StopTime.arrivo_teorico.label('arr_time'),
                StopTime.partenza_teorica.label('dep_time'),
                Train.codOrigine.label('origin_id'),
                Train.destinazione.label('destination'),
                Train.numeroTreno.label('trip_id'),
                Train.dataPartenzaTreno.label('origin_dep_time'),
                StopTime.binario.label('platform'),
                Train.categoria.label('route_name')
            )

        raw_stop_times = raw_stop_times \
            .select_from(StopTime) \
            .join(Train, StopTime.train_id == Train.id) \
            .filter(
            and_(
                StopTime.idFermata == station_id,
                StopTime.partenza_teorica >= start_dt,
                StopTime.partenza_teorica < end_dt
            )
        )

        if line != '':
            raw_stop_times = raw_stop_times.filter(Train.categoria == line)

        if count:
            raw_stop_times = raw_stop_times \
                .group_by(Train.categoria) \
                .order_by(func.count(Train.categoria).desc())
        else:
            raw_stop_times = raw_stop_times.order_by(StopTime.partenza_teorica).limit(self.LIMIT).offset(offset_times)

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

    def loop_get_times(self, limit, stop: Stop, dt, train_ids=None, type='partenze') -> list[TrenitaliaStopTime]:
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

    def get_stop_times_from_start_dt(self, type, stop: Stop, start_dt: datetime, train_ids: list[int] | None) -> \
            list[TrenitaliaStopTime]:
        is_dst = start_dt.astimezone().dst() != timedelta(0)
        date = (start_dt - timedelta(hours=(1 if is_dst else 0))).strftime("%a %b %d %Y %H:%M:%S GMT+0100")
        url = f'http://www.viaggiatreno.it/infomobilita/resteasy/viaggiatreno/{type}/{stop.ref}/{quote(date)}'
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

    def get_stop_times_between_stops(self, dep_stop: Stop, arr_stop: Stop, line, start_time,
                                     offset_times, day,
                                     context: ContextTypes.DEFAULT_TYPE | None = None, count=False):
        day_start = datetime.combine(day, time(0))

        if start_time == '':
            start_dt = day_start
        else:
            start_dt = datetime.combine(day, start_time) - timedelta(minutes=self.MINUTES_TOLERANCE)

        end_dt = day_start + timedelta(days=1)

        dep_station_id = next(iter(dep_stop.ids))
        arr_station_id = next(iter(arr_stop.ids))

        # Define alias for stop_times
        a_stop_times = aliased(StopTime)
        d_stop_times = aliased(StopTime)

        if count:
            raw_stop_times = self.session.query(
                Train.categoria.label('route_name'),
            )
        else:
            raw_stop_times = self.session.query(
                d_stop_times.arrivo_teorico.label('d_arr_time'),
                d_stop_times.partenza_teorica.label('d_dep_time'),
                Train.codOrigine.label('origin_id'),
                Train.destinazione.label('destination'),
                Train.numeroTreno.label('trip_id'),
                Train.dataPartenzaTreno.label('origin_dep_time'),
                Train.categoria.label('route_name'),
                d_stop_times.binario.label('d_platform'),
                a_stop_times.partenza_teorica.label('a_dep_time'),
                a_stop_times.arrivo_teorico.label('a_arr_time'),
                a_stop_times.binario.label('a_platform')
            )

        raw_stop_times = raw_stop_times \
            .select_from(d_stop_times) \
            .join(a_stop_times, d_stop_times.train_id == a_stop_times.train_id) \
            .join(Train, d_stop_times.train_id == Train.id) \
            .filter(
            and_(
                d_stop_times.idFermata == dep_station_id,
                d_stop_times.partenza_teorica >= start_dt,
                d_stop_times.partenza_teorica < end_dt,
                d_stop_times.partenza_teorica < a_stop_times.arrivo_teorico,
                a_stop_times.idFermata == arr_station_id
            )
        )

        if line != '':
            raw_stop_times = raw_stop_times.filter(Train.categoria == line)

        if count:
            raw_stop_times = raw_stop_times.group_by(Train.categoria).order_by(func.count(Train.categoria).desc())
        else:
            raw_stop_times = raw_stop_times.order_by(
                d_stop_times.partenza_teorica
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
        query = select(StopTime, Train, Station) \
            .join(StopTime.train) \
            .join(StopTime.station) \
            .filter(
            and_(
                Train.numeroTreno == trip_id,
                Train.dataPartenzaTreno == day.isoformat()
            )) \
            .order_by(StopTime.partenza_teorica)

        results = self.session.execute(query)

        stop_times = []
        for result in results:
            stop = Stop(result.Station.id, result.Station.name, [result.Station.id])
            stop_time = TrenitaliaStopTime(stop, result.Train.codOrigine, result.StopTime.partenza_teorica, None, 0,
                                           result.StopTime.binario, result.Train.destinazione, trip_id,
                                           result.Train.categoria,
                                           result.StopTime.arrivo_teorico, result.Train.dataPartenzaTreno)
            stop_times.append(stop_time)

        return stop_times
