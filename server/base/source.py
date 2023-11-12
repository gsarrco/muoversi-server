import logging
from datetime import datetime, date, timedelta, time

from sqlalchemy import select, func, and_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import aliased
from telegram.ext import ContextTypes

from .models import Station, Stop, StopTime

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


class Liner:
    def format(self, number, _, source_name):
        raise NotImplementedError


class BaseStopTime(Liner):
    def __init__(self, station: 'Station', dep_time: datetime | None, arr_time: datetime | None, stop_sequence,
                 delay: int,
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

    def search_stops(self, name=None, lat=None, lon=None, page=1, limit=4, all_sources=False) -> tuple[
        list[Station], int]:
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

    def get_stop_times(self, stops_ids, line, start_time, day,
                       offset_times, count=False, limit=True) -> list[StopTime] | list[str]:
        day_start = datetime.combine(day, time(0))

        if start_time == '':
            start_dt = day_start
        else:
            start_dt = datetime.combine(day, start_time) - timedelta(minutes=self.MINUTES_TOLERANCE)

        end_dt = day_start + timedelta(days=1)

        stops_ids = stops_ids.split(',')

        if count:
            stmt = select(StopTime.route_name)
        else:
            stmt = select(StopTime)

        day_minus_one = day - timedelta(days=1)

        stmt = stmt \
            .filter(
            and_(
                StopTime.orig_dep_date.between(day_minus_one, day),
                StopTime.stop_id.in_(stops_ids),
                StopTime.sched_dep_dt >= start_dt,
                StopTime.sched_dep_dt < end_dt
            )
        )

        if line != '':
            stmt = stmt.filter(StopTime.route_name == line)

        if count:
            stmt = stmt \
                .group_by(StopTime.route_name) \
                .order_by(func.count(StopTime.route_name).desc())
            stop_times = self.session.execute(stmt).all()
        else:
            stmt = stmt.order_by(StopTime.sched_dep_dt).limit(self.LIMIT).offset(offset_times)
            stop_times = self.session.scalars(stmt).all()

        if count:
            return [train.route_name for train in stop_times]

        return stop_times

    def get_stop_times_between_stops(self, dep_stops_ids, arr_stops_ids, line, start_time,
                                     offset_times, day, context: ContextTypes.DEFAULT_TYPE | None = None, count=False) \
            -> list[tuple[StopTime, StopTime]] | list[str]:
        day_start = datetime.combine(day, time(0))

        if start_time == '':
            start_dt = day_start
        else:
            start_dt = datetime.combine(day, start_time) - timedelta(minutes=self.MINUTES_TOLERANCE)

        end_dt = day_start + timedelta(days=1)

        dep_stops_ids = dep_stops_ids.split(',')
        arr_stops_ids = arr_stops_ids.split(',')

        # Define alias for stop_times
        a_stop_times = aliased(StopTime)
        d_stop_times = aliased(StopTime)

        if count:
            stmt = select(d_stop_times.route_name)
        else:
            stmt = select(d_stop_times, a_stop_times)
            

        day_minus_one = day - timedelta(days=1)

        stmt = stmt \
            .select_from(d_stop_times) \
            .join(a_stop_times, and_(d_stop_times.number == a_stop_times.number,
                                     d_stop_times.orig_dep_date == a_stop_times.orig_dep_date,
                                     d_stop_times.source == a_stop_times.source)) \
            .filter(
            and_(
                d_stop_times.orig_dep_date.between(day_minus_one, day),
                d_stop_times.stop_id.in_(dep_stops_ids),
                d_stop_times.sched_dep_dt >= start_dt,
                d_stop_times.sched_dep_dt < end_dt,
                d_stop_times.sched_dep_dt < a_stop_times.sched_arr_dt,
                a_stop_times.stop_id.in_(arr_stops_ids)
            )
        )

        if line != '':
            stmt = stmt.filter(d_stop_times.route_name == line)

        if count:
            stmt = stmt.group_by(d_stop_times.route_name).order_by(
                func.count(d_stop_times.route_name).desc())
        else:
            stmt = stmt.order_by(
                d_stop_times.sched_dep_dt
            ).limit(self.LIMIT).offset(offset_times)

        raw_stop_times = self.session.execute(stmt).all()

        if count:
            return [train.route_name for train in raw_stop_times]

        stop_times_tuples: list[tuple[StopTime, StopTime]] = []

        for raw_stop_time in raw_stop_times:
            d_stop_time, a_stop_time = raw_stop_time
            stop_times_tuples.append((d_stop_time, a_stop_time))

        return stop_times_tuples

    def sync_stations_db(self, new_stations: list[Station], new_stops: list[Stop] = None):
        station_codes = [s.id for s in new_stations]

        for station in new_stations:
            stmt = insert(Station).values(id=station.id, name=station.name, lat=station.lat, lon=station.lon,
                                          ids=station.ids, source=self.name, times_count=station.times_count,
                                          active=True)
            stmt = stmt.on_conflict_do_update(
                index_elements=['id'],
                set_={'name': station.name, 'lat': station.lat, 'lon': station.lon, 'ids': station.ids,
                      'source': self.name, 'times_count': station.times_count, 'active': True}
            )
            self.session.execute(stmt)

        for station in self.session.scalars(select(Station).filter_by(source=self.name, active=True)).all():
            if station.id not in station_codes:
                # set station as inactive and set all stops as inactive
                station.active = False
                for stop in station.stops:
                    stop.active = False



        self.session.commit()

        stop_ids = [s.id for s in new_stops] if new_stops else station_codes

        if new_stops:
            for stop in new_stops:
                stmt = insert(Stop).values(id=stop.id, platform=stop.platform, lat=stop.lat, lon=stop.lon,
                                           station_id=stop.station_id, source=self.name, active=True)
                stmt = stmt.on_conflict_do_update(
                    index_elements=['id'],
                    set_={'platform': stop.platform, 'lat': stop.lat, 'lon': stop.lon,
                          'station_id': stop.station_id, 'source': self.name, 'active': True}
                )
                self.session.execute(stmt)
        else:
            for station in new_stations:
                stmt = insert(Stop).values(id=station.id, platform=None, lat=station.lat, lon=station.lon,
                                           station_id=station.id, source=self.name, active=True)
                stmt = stmt.on_conflict_do_update(
                    index_elements=['id'],
                    set_={'platform': None, 'lat': station.lat, 'lon': station.lon,
                          'station_id': station.id, 'source': self.name, 'active': True}
                )
                self.session.execute(stmt)

        # Stops with stations not in station_codes are set as inactive
        for stop in self.session.scalars(select(Stop).filter(Stop.station_id.in_(station_codes), Stop.active is True)).all():
            if stop.id not in stop_ids:
                stop.active = False

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

    def search_lines(self, name):
        raise NotImplementedError

    def get_source_stations(self) -> list[Station]:
        return self.session.scalars(select(Station).filter_by(source=self.name, active=True)).all()
    
    def upload_trip_stop_time_to_postgres(self, stop_time: TripStopTime):
        stop_id = self.name + '_' + stop_time.station.id if self.name != 'treni' else stop_time.station.id

        stmt = insert(StopTime).values(stop_id=stop_id, sched_arr_dt=stop_time.arr_time,
                                        sched_dep_dt=stop_time.dep_time, platform=stop_time.platform,
                                        orig_id=stop_time.origin_id, dest_text=stop_time.destination,
                                        number=stop_time.trip_id, orig_dep_date=stop_time.orig_dep_date,
                                        route_name=stop_time.route_name, source=self.name)

        stmt = stmt.on_conflict_do_update(
            index_elements=['stop_id', 'number', 'orig_dep_date', 'source'],
            set_={'platform': stop_time.platform}
        )

        self.session.execute(stmt)
        self.session.commit()

    def get_stops_from_trip_id(self, trip_id, day: date) -> list[BaseStopTime]:
        trip_id = int(trip_id)
        query = select(StopTime, Stop) \
            .join(StopTime.stop) \
            .filter(
            and_(
                StopTime.number == trip_id,
                StopTime.orig_dep_date == day.isoformat()
            )) \
            .order_by(StopTime.sched_dep_dt)

        results = self.session.execute(query).all()

        stop_times = []
        for result in results:
            stop_time = TripStopTime(result.Stop, result.StopTime.orig_id, result.StopTime.sched_dep_dt,
                                     None, 0,
                                     result.StopTime.platform, result.StopTime.dest_text, trip_id,
                                     result.StopTime.route_name,
                                     result.StopTime.sched_arr_dt, result.StopTime.orig_dep_date)
            stop_times.append(stop_time)

        return stop_times
