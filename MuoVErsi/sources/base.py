import logging
from datetime import datetime, date
from typing import Optional

from sqlalchemy import select, func, ForeignKey, UniqueConstraint, String
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Mapped, mapped_column, relationship, declarative_base
from telegram.ext import ContextTypes

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


class Stop:
    def __init__(self, ref: str = None, name: str = None, ids=None):
        if ids is None:
            ids = []
        self.ref = ref
        self.name = name
        self.ids = ids


class Liner:
    def format(self, number, _, source_name):
        raise NotImplementedError


class BaseStopTime(Liner):
    def __init__(self, stop: Stop, dep_time: datetime | None, arr_time: datetime | None, stop_sequence, delay: int,
                 platform,
                 headsign, trip_id,
                 route_name):
        self.stop = stop
        self.dep_time = dep_time
        self.arr_time = arr_time
        self.stop_sequence = stop_sequence
        self.delay = delay
        self.platform = platform
        self.headsign = headsign
        self.trip_id = trip_id
        self.route_name = route_name

    def format(self, number, _, source_name, left_time_bold=True, right_time_bold=True):
        headsign, trip_id, stop_sequence = self.headsign, self.trip_id, self.stop_sequence

        # First line of text
        time_format = ""

        if left_time_bold:
            time_format += "<b>"

        time_format += self.dep_time.strftime('%H:%M')

        if self.delay > 0:
            time_format += f'+{self.delay}m'

        if left_time_bold:
            time_format += "</b>"

        headsign = headsign[:21]
        route_name = f'{self.route_name} ' if self.route_name else ''
        line = f'{time_format} {route_name}{headsign}'

        # Second line of text
        trip_id = f'/{self.trip_id} ' if self.trip_id else ''
        platform = self.platform if self.platform else '/'
        platform_text = _(f'{source_name}_platform')
        line += f'\n⎿ <i>{trip_id}{platform_text} {platform}</i>'

        # Modifications for all lines of text
        if self.dep_time < datetime.now():
            line = f'<del>{line}</del>'

        if number:
            return f'\n{number}. {line}'
        else:
            return f'\n⎿ {line}'


class Route(Liner):
    def __init__(self, dep_stop_time: BaseStopTime, arr_stop_time: BaseStopTime | None):
        self.dep_stop_time = dep_stop_time
        self.arr_stop_time = arr_stop_time

    def format(self, number, _, source_name, left_time_bold=True, right_time_bold=True):
        line, headsign, trip_id, stop_sequence = self.dep_stop_time.route_name, self.dep_stop_time.headsign, \
            self.dep_stop_time.trip_id, self.dep_stop_time.stop_sequence

        # First line of text
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

        headsign = headsign[:14]
        route_name = f'{self.dep_stop_time.route_name} ' if self.dep_stop_time.route_name else ''
        line = f'{time_format} {route_name}{headsign}'

        # Second line of text
        platform_text = _(f'{source_name}_platform')
        dep_platform = self.dep_stop_time.platform if self.dep_stop_time.platform else '/'
        arr_platform = self.arr_stop_time.platform if self.arr_stop_time.platform else '/'
        line += f'\n⎿ <i>/{self.dep_stop_time.trip_id} {platform_text} {dep_platform} -> {arr_platform}</i>'

        # Modifications for all lines of text
        if self.dep_stop_time.dep_time < datetime.now():
            line = f'<del>{line}</del>'

        if number:
            return f'\n{number}. {line}'
        else:
            return f'\n⎿ {line}'


class Direction(Liner):
    def __init__(self, routes: list[Route]):
        self.routes = routes

    def format(self, number, _, source_name):
        text = ""
        for i, route in enumerate(self.routes):
            number = number if i == 0 else None
            text += route.format(number, _, source_name, left_time_bold=i == 0,
                                 right_time_bold=i == len(self.routes) - 1)

            if route.arr_stop_time.stop.name and i != len(self.routes) - 1:
                next_route = self.routes[i + 1]
                print(route.arr_stop_time.dep_time, next_route.dep_stop_time.dep_time)
                duration_in_minutes = (next_route.dep_stop_time.dep_time - route.arr_stop_time.dep_time).seconds // 60
                text += f'\n⎿ <i>cambio a {route.arr_stop_time.stop.name} ({duration_in_minutes}min)</i>'

        return text

Base = declarative_base()


class Station(Base):
    __tablename__ = 'stations'

    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    lat: Mapped[Optional[float]]
    lon: Mapped[Optional[float]]
    ids: Mapped[str] = mapped_column(server_default='')
    times_count: Mapped[float] = mapped_column(server_default='0')
    source: Mapped[str] = mapped_column(server_default='treni')
    stop_times = relationship('StopTime', back_populates='station', cascade='all, delete-orphan')


class Source:
    LIMIT = 7
    MINUTES_TOLERANCE = 3

    def __init__(self, name, session):
        self.name = name
        self.session = session

    def search_stops(self, name=None, lat=None, lon=None, limit=4) -> list[Stop]:
        stmt = select(Station)
        if lat and lon:
            stmt = stmt \
                .filter(Station.lat.isnot(None), Station.source == self.name) \
                .order_by(func.abs(Station.lat - lat) + func.abs(Station.lon - lon))
        else:
            stmt = stmt \
                .filter(Station.name.ilike(f'%{name}%'), Station.source == self.name) \
                .order_by(Station.times_count.desc())
        results = self.session.scalars(stmt.limit(limit)).all()

        stops = []
        for result in results:
            stops.append(Stop(result.id, result.name, result.ids.split(',')))

        return stops

    def get_stop_times(self, stop: Stop, line, start_time, day,
                       offset_times, context: ContextTypes.DEFAULT_TYPE | None = None, count=False):
        raise NotImplementedError

    def get_stop_times_between_stops(self, dep_stop: Stop, arr_stop: Stop, line, start_time,
                                     offset_times, day,
                                     context: ContextTypes.DEFAULT_TYPE | None = None, count=False):
        raise NotImplementedError

    def sync_stations_db(self, new_stations: list[Station]):
        station_codes = [s.id for s in new_stations]

        for station in new_stations:
            stmt = insert(Station).values(id=station.id, name=station.name, lat=station.lat, lon=station.lon,
                                          ids=station.ids, source=self.name, times_count=station.times_count)
            stmt = stmt.on_conflict_do_update(
                index_elements=['id'],
                set_={'name': station.name, 'lat': station.lat, 'lon': station.lon, 'ids': station.ids,
                      'source': self.name, 'times_count': station.times_count}
            )
            self.session.execute(stmt)

        for station in self.session.scalars(select(Station).filter_by(source=self.name)).all():
            if station.id not in station_codes:
                self.session.delete(station)

        self.session.commit()

    def get_stop_from_ref(self, ref):
        stmt = select(Station) \
            .filter(Station.id == ref, Station.source == self.name)
        result: Station = self.session.scalars(stmt).first()
        if result:
            return Stop(result.id, result.name, result.ids.split(','))
        else:
            return None

    def search_lines(self, name, context: ContextTypes.DEFAULT_TYPE | None = None):
        raise NotImplementedError

    def get_stops_from_trip_id(self, trip_id, day: date) -> list[BaseStopTime]:
        raise NotImplementedError


class Train(Base):
    __tablename__ = 'trains'

    id: Mapped[int] = mapped_column(primary_key=True)
    codOrigine: Mapped[str]
    destinazione: Mapped[str]
    numeroTreno: Mapped[int]
    dataPartenzaTreno: Mapped[date]
    statoTreno: Mapped[str] = mapped_column(String, default='regol.')
    categoria: Mapped[str]
    stop_times = relationship('StopTime', back_populates='train')

    __table_args__ = (UniqueConstraint('codOrigine', 'numeroTreno', 'dataPartenzaTreno'),)


class StopTime(Base):
    __tablename__ = 'stop_times'

    id: Mapped[int] = mapped_column(primary_key=True)
    train_id: Mapped[int] = mapped_column(ForeignKey('trains.id'))
    train: Mapped[Train] = relationship('Train', back_populates='stop_times')
    idFermata: Mapped[str] = mapped_column(ForeignKey('stations.id'))
    station: Mapped[Station] = relationship('Station', back_populates='stop_times')
    arrivo_teorico: Mapped[Optional[datetime]]
    arrivo_reale: Mapped[Optional[datetime]]
    partenza_teorica: Mapped[Optional[datetime]]
    partenza_reale: Mapped[Optional[datetime]]
    ritardo_arrivo: Mapped[Optional[int]]
    ritardo_partenza: Mapped[Optional[int]]
    binario: Mapped[Optional[str]]

    __table_args__ = (UniqueConstraint('train_id', 'idFermata'),)
