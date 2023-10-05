import logging
from datetime import datetime, date, timedelta, time
from typing import Optional

from sqlalchemy import select, ForeignKey, UniqueConstraint, func, and_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Mapped, mapped_column, relationship, declarative_base, aliased
from telegram.ext import ContextTypes

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


class Liner:
    def format(self, number, _, source_name):
        raise NotImplementedError
    




class BaseStopTime(Liner):
    def __init__(self, station: 'Station', dep_time: datetime | None, arr_time: datetime | None, stop_sequence, delay: int,
                 platform,
                 headsign, trip_id,
                 route_name):
        self.station = station
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

            if route.arr_stop_time.station.name and i != len(self.routes) - 1:
                next_route = self.routes[i + 1]
                print(route.arr_stop_time.dep_time, next_route.dep_stop_time.dep_time)
                duration_in_minutes = (next_route.dep_stop_time.dep_time - route.arr_stop_time.dep_time).seconds // 60
                text += f'\n⎿ <i>cambio a {route.arr_stop_time.station.name} ({duration_in_minutes}min)</i>'

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
    stops = relationship('Stop', back_populates='station', cascade='all, delete-orphan')


class Stop(Base):
    __tablename__ = 'stops'

    id: Mapped[str] = mapped_column(primary_key=True)
    platform: Mapped[Optional[str]]
    lat: Mapped[float]
    lon: Mapped[float]
    station_id: Mapped[str] = mapped_column(ForeignKey('stations.id'))
    station: Mapped[Station] = relationship('Station', back_populates='stops')
    source: Mapped[Optional[str]]
    stop_times = relationship('StopTime', back_populates='stop', cascade='all, delete-orphan')


class TripStopTime(BaseStopTime):
    def __init__(self, station: Station, origin_id, dep_time: datetime | None, stop_sequence, delay: int, platform,
                 headsign,
                 trip_id,
                 route_name,
                 arr_time: datetime = None,
                 orig_dep_date: date = None, destination: str = None):
        if arr_time is None:
            arr_time = dep_time
        super().__init__(station, dep_time, arr_time, stop_sequence, delay, platform, headsign, trip_id, route_name)
        self.orig_dep_date = orig_dep_date
        self.destination = destination
        self.origin_id = origin_id

    def merge(self, arr_stop_time: 'TripStopTime'):
        self.arr_time = arr_stop_time.arr_time


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
    
    def get_stop_times(self, station: Station, line, start_time, day,
                       offset_times, count=False, limit=True):
        day_start = datetime.combine(day, time(0))

        if start_time == '':
            start_dt = day_start
        else:
            start_dt = datetime.combine(day, start_time) - timedelta(minutes=self.MINUTES_TOLERANCE)

        end_dt = day_start + timedelta(days=1)

        stops_ids = station.ids.split(',')

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
                Trip.orig_dep_date.label('orig_dep_date'),
                StopTime.platform.label('platform'),
                Trip.route_name.label('route_name')
            )

        raw_stop_times = raw_stop_times \
            .select_from(StopTime) \
            .join(Trip, StopTime.trip_id == Trip.id) \
            .filter(
            and_(
                StopTime.stop_id.in_(stops_ids),
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
            stop_time = TripStopTime(station, raw_stop_time.origin_id, dep_time, None, 0, raw_stop_time.platform,
                                           raw_stop_time.destination, raw_stop_time.trip_id,
                                           raw_stop_time.route_name, arr_time=arr_time,
                                           orig_dep_date=raw_stop_time.orig_dep_date)
            stop_times.append(stop_time)

        return stop_times

    def get_stop_times_between_stops(self, dep_station: Station, arr_station: Station, line, start_time,
                                     offset_times, day,
                                     context: ContextTypes.DEFAULT_TYPE | None = None, count=False):
        day_start = datetime.combine(day, time(0))

        if start_time == '':
            start_dt = day_start
        else:
            start_dt = datetime.combine(day, start_time) - timedelta(minutes=self.MINUTES_TOLERANCE)

        end_dt = day_start + timedelta(days=1)

        dep_stops_ids = dep_station.ids.split(',')
        arr_stops_ids = arr_station.ids.split(',')

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
                Trip.orig_dep_date.label('orig_dep_date'),
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
                d_stop_times.stop_id.in_(dep_stops_ids),
                d_stop_times.sched_dep_dt >= start_dt,
                d_stop_times.sched_dep_dt < end_dt,
                d_stop_times.sched_dep_dt < a_stop_times.sched_arr_dt,
                a_stop_times.stop_id.in_(arr_stops_ids)
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
            d_stop_time = TripStopTime(
                dep_station, raw_stop_time.origin_id, d_dep_time, None, 0, raw_stop_time.d_platform,
                raw_stop_time.destination, raw_stop_time.trip_id, raw_stop_time.route_name,
                arr_time=d_arr_time, orig_dep_date=raw_stop_time.orig_dep_date)

            a_stop_time = TripStopTime(
                arr_station, raw_stop_time.origin_id, a_dep_time, None, 0, raw_stop_time.a_platform,
                raw_stop_time.destination, raw_stop_time.trip_id, raw_stop_time.route_name,
                arr_time=a_arr_time, orig_dep_date=raw_stop_time.orig_dep_date)

            from MuoVErsi.sources.trenitalia import TrenitaliaRoute
            route = TrenitaliaRoute(d_stop_time, a_stop_time)
            directions.append(Direction([route]))

        return directions

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
                                           station_id=stop.station_id, source=self.name)
                stmt = stmt.on_conflict_do_update(
                    index_elements=['id'],
                    set_={'platform': stop.platform, 'lat': stop.lat, 'lon': stop.lon,
                          'station_id': stop.station_id, 'source': self.name}
                )
                self.session.execute(stmt)
        else:
            for station in new_stations:
                stmt = insert(Stop).values(id=station.id, platform=None, lat=station.lat, lon=station.lon,
                                           station_id=station.id, source=self.name)
                stmt = stmt.on_conflict_do_update(
                    index_elements=['id'],
                    set_={'platform': None, 'lat': station.lat, 'lon': station.lon,
                          'station_id': station.id, 'source': self.name}
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

        stations_to_sync = [{
            'id': station.id,
            'name': station.name,
            'location': [station.lat, station.lon],
            'ids': station.ids,
            'source': station.source,
            'times_count': station.times_count
        } for station in stations]

        if not stations_to_sync:
            return

        stations_collection.documents.import_(stations_to_sync)

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
    
    def upload_trip_stop_times_to_postgres(self, stop_times: list[TripStopTime]):
        for stop_time in stop_times:
            train = self.session.query(Trip).filter_by(
                number=stop_time.trip_id,
                orig_dep_date=stop_time.orig_dep_date,
                source=self.name
            ).first()

            if not train:
                train = Trip(orig_id=stop_time.origin_id, dest_text=stop_time.destination,
                                number=stop_time.trip_id, orig_dep_date=stop_time.orig_dep_date,
                                route_name=stop_time.route_name, source=self.name)
                self.session.add(train)
                self.session.commit()

            stop_id = self.name + '_' + stop_time.station.id if self.name != 'treni' else stop_time.station.id
            stop_time_db = self.session.query(StopTime).filter_by(trip_id=train.id, stop_id=stop_id).first()

            if stop_time_db:
                if stop_time_db.platform != stop_time.platform:
                    stop_time_db.platform = stop_time.platform
                    self.session.commit()
            else:
                new_stop_time = StopTime(trip_id=train.id, stop_id=stop_id, sched_arr_dt=stop_time.arr_time,
                                            sched_dep_dt=stop_time.dep_time, platform=stop_time.platform)
                self.session.add(new_stop_time)
                self.session.commit()


class Trip(Base):
    __tablename__ = 'trips'

    id: Mapped[int] = mapped_column(primary_key=True)
    orig_id: Mapped[str]
    dest_text: Mapped[str]
    number: Mapped[int]
    orig_dep_date: Mapped[date]
    route_name: Mapped[str]
    source: Mapped[str] = mapped_column(server_default='treni')
    stop_times = relationship('StopTime', back_populates='trip', cascade='all, delete-orphan', passive_deletes=True)

    __table_args__ = (UniqueConstraint('source', 'number', 'orig_dep_date'),)


class StopTime(Base):
    __tablename__ = 'stop_times'

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey('trips.id', ondelete='CASCADE'))
    trip: Mapped[Trip] = relationship('Trip', back_populates='stop_times')
    stop_id: Mapped[str] = mapped_column(ForeignKey('stops.id'))
    stop: Mapped[Stop] = relationship('Stop', back_populates='stop_times')
    sched_arr_dt: Mapped[Optional[datetime]]
    sched_dep_dt: Mapped[Optional[datetime]]
    platform: Mapped[Optional[str]]

    __table_args__ = (UniqueConstraint('trip_id', 'stop_id'),)
