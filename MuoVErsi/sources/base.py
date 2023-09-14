import logging
from datetime import datetime, date
from typing import Optional

from sqlalchemy import select, ForeignKey, UniqueConstraint, String
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Mapped, mapped_column, relationship, declarative_base
from telegram.ext import ContextTypes

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


class Liner:
    def format(self, number, _, source_name):
        raise NotImplementedError


class BaseStopTime(Liner):
    def __init__(self, stop: 'Station', dep_time: datetime | None, arr_time: datetime | None, stop_sequence, delay: int,
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
    stops = relationship('Stop', back_populates='station', cascade='all, delete-orphan')


class Stop(Base):
    __tablename__ = 'stops'

    id: Mapped[str] = mapped_column(primary_key=True)
    platform: Mapped[Optional[str]]
    lat: Mapped[float]
    lon: Mapped[float]
    station_id: Mapped[str] = mapped_column(ForeignKey('stations.id'))
    station: Mapped[Station] = relationship('Station', back_populates='stops')


class Source:
    LIMIT = 7
    MINUTES_TOLERANCE = 3

    def __init__(self, name, emoji, session, typesense):
        self.name = name
        self.emoji = emoji
        self.session = session
        self.typesense = typesense

    def search_stops(self, name=None, lat=None, lon=None, page=1, limit=4, all_sources=False) -> tuple[list[Station], int]:
        search_config = {'per_page': limit, 'query_by': 'name', 'page': page}

        limit_hits = None
        if lat and lon:
            limit_hits = limit * 2
            search_config.update({
                'q': '*',
                'sort_by': f'location({lat},{lon}):asc',
                'limit_hits': limit_hits
            })
        else:
            search_config.update({
                'q': name,
                'sort_by': 'times_count:desc'
            })
        if not all_sources:
            search_config['filter_by'] = f'source:{self.name}'

        results = self.typesense.collections['stations'].documents.search(search_config)

        stations = []

        for result in results['hits']:
            document = result['document']
            lat, lon = document['location']
            station = Station(id=document['id'], name=document['name'], lat=lat, lon=lon,
                              ids=document['ids'], source=document['source'], times_count=document['times_count'])
            stations.append(station)

        found = limit_hits if limit_hits else results['found']
        return stations, found

    def get_stop_times(self, stop: Station, line, start_time, day,
                       offset_times, context: ContextTypes.DEFAULT_TYPE | None = None, count=False):
        raise NotImplementedError

    def get_stop_times_between_stops(self, dep_stop: Station, arr_stop: Station, line, start_time,
                                     offset_times, day,
                                     context: ContextTypes.DEFAULT_TYPE | None = None, count=False):
        raise NotImplementedError

    def sync_stations_db(self, new_stations: list[Station], new_stops: list[Stop] = None):
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

        stop_ids = [s.id for s in new_stops] if new_stops else station_codes

        if new_stops:
            for stop in new_stops:
                stmt = insert(Stop).values(id=stop.id, platform=stop.platform, lat=stop.lat, lon=stop.lon,
                                           station_id=stop.station_id)
                stmt = stmt.on_conflict_do_update(
                    index_elements=['id'],
                    set_={'platform': stop.platform, 'lat': stop.lat, 'lon': stop.lon,
                          'station_id': stop.station_id}
                )
                self.session.execute(stmt)
        else:
            for station in new_stations:
                stmt = insert(Stop).values(id=station.id, platform=None, lat=station.lat, lon=station.lon,
                                           station_id=station.id)
                stmt = stmt.on_conflict_do_update(
                    index_elements=['id'],
                    set_={'platform': None, 'lat': station.lat, 'lon': station.lon,
                          'station_id': station.id}
                )
                self.session.execute(stmt)

        # Stops with stations not in station_codes are deleted through cascade
        for stop in self.session.scalars(select(Stop).filter(Stop.station_id.in_(station_codes))).all():
            if stop.id not in stop_ids:
                self.session.delete(stop)

        self.session.commit()

        self.sync_stations_typesense(new_stations)

    def sync_stations_typesense(self, stations: list[Station]):
        stations_collection = self.typesense.collections['stations']

        stations_collection.documents.delete({'filter_by': f'source:{self.name}'})

        stations_collection.documents.import_([{
            'id': station.id,
            'name': station.name,
            'location': [station.lat, station.lon],
            'ids': station.ids,
            'source': station.source,
            'times_count': station.times_count
        } for station in stations])

    def get_stop_from_ref(self, ref) -> Station | None:
        stmt = select(Station) \
            .filter(Station.id == ref, Station.source == self.name)
        result: Station = self.session.scalars(stmt).first()
        if result:
            return result
        else:
            return None

    def search_lines(self, name, context: ContextTypes.DEFAULT_TYPE | None = None):
        raise NotImplementedError

    def get_stops_from_trip_id(self, trip_id, day: date) -> list[BaseStopTime]:
        raise NotImplementedError

    def get_source_stations(self) -> list[Station]:
        return self.session.scalars(select(Station).filter_by(source=self.name)).all()


class Trip(Base):
    __tablename__ = 'trips'

    id: Mapped[int] = mapped_column(primary_key=True)
    orig_id: Mapped[str]
    dest_text: Mapped[str]
    number: Mapped[int]
    orig_dep_date: Mapped[date]
    route_name: Mapped[str]
    stop_times = relationship('StopTime', back_populates='trip')

    __table_args__ = (UniqueConstraint('orig_id', 'number', 'orig_dep_date'),)


class StopTime(Base):
    __tablename__ = 'stop_times'

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey('trips.id'))
    trip: Mapped[Trip] = relationship('Trip', back_populates='stop_times')
    stop_id: Mapped[str] = mapped_column(ForeignKey('stations.id'))
    station: Mapped[Station] = relationship('Station', back_populates='stop_times')
    sched_arr_dt: Mapped[Optional[datetime]]
    sched_dep_dt: Mapped[Optional[datetime]]
    platform: Mapped[Optional[str]]

    __table_args__ = (UniqueConstraint('trip_id', 'stop_id'),)
