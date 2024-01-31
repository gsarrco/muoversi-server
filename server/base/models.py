from datetime import date, datetime
from typing import Optional
from pytz import timezone

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import declarative_base, Mapped, mapped_column, relationship
from sqlalchemy_utc import UtcDateTime

Base = declarative_base()


class City(Base):
    __tablename__ = 'cities'

    name: Mapped[str] = mapped_column(primary_key=True)
    sources = relationship('DBSource', back_populates='city')


class DBSource(Base):
    __tablename__ = 'sources'
    name: Mapped[str] = mapped_column(primary_key=True)
    city_name: Mapped[str] = mapped_column(ForeignKey('cities.name'))
    city: Mapped[City] = relationship('City', back_populates='sources')
    color: Mapped[str]
    icon_code: Mapped[int]

    def as_dict(self):
        return {
            'name': self.name,
            'color': self.color,
            'icon_code': self.icon_code
        }


class Station(Base):
    __tablename__ = 'stations'

    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    lat: Mapped[Optional[float]]
    lon: Mapped[Optional[float]]
    ids: Mapped[str] = mapped_column(server_default='')
    times_count: Mapped[float] = mapped_column(server_default='0')
    source: Mapped[str] = mapped_column(ForeignKey('sources.name'))
    stops = relationship('Stop', back_populates='station', cascade='all, delete-orphan')
    active: Mapped[bool] = mapped_column(server_default='true')

    def as_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'lat': self.lat,
            'lon': self.lon,
            'source': self.source,
            'ids': self.ids
        }


class Stop(Base):
    __tablename__ = 'stops'

    id: Mapped[str] = mapped_column(primary_key=True)
    platform: Mapped[Optional[str]]
    lat: Mapped[float]
    lon: Mapped[float]
    station_id: Mapped[str] = mapped_column(ForeignKey('stations.id'))
    station: Mapped[Station] = relationship('Station', back_populates='stops')
    source: Mapped[str] = mapped_column(ForeignKey('sources.name'))
    active: Mapped[bool] = mapped_column(server_default='true')


class StopTime(Base):
    __tablename__ = 'stop_times'

    id: Mapped[int] = mapped_column(primary_key=True)
    sched_arr_dt: Mapped[Optional[datetime]] = mapped_column(UtcDateTime)
    sched_dep_dt: Mapped[Optional[datetime]] = mapped_column(UtcDateTime)
    orig_dep_date: Mapped[date]
    platform: Mapped[Optional[str]]
    orig_id: Mapped[str]
    dest_text: Mapped[str]
    number: Mapped[int]
    route_name: Mapped[str]
    source: Mapped[str] = mapped_column(ForeignKey('sources.name'))
    stop_id: Mapped[str] = mapped_column(ForeignKey('stops.id'))
    stop: Mapped[Stop] = relationship('Stop', foreign_keys=stop_id)
    
    def tz_sched_arr_dt(self):
        return self.sched_arr_dt.astimezone(timezone('Etc/GMT+1'))
    
    def tz_sched_dep_dt(self):
        return self.sched_dep_dt.astimezone(timezone('Etc/GMT+1'))
    
    __table_args__ = (UniqueConstraint("stop_id", "number", "source", "orig_dep_date"),)

    def as_dict(self):
        return {
            'id': self.id,
            'sched_arr_dt': self.tz_sched_arr_dt().replace(tzinfo=None).isoformat() if self.sched_arr_dt else None,
            'sched_dep_dt': self.tz_sched_dep_dt().replace(tzinfo=None).isoformat() if self.sched_dep_dt else None,
            'orig_dep_date': self.orig_dep_date.isoformat(),
            'platform': self.platform,
            'orig_id': self.orig_id,
            'dest_text': self.dest_text,
            'number': self.number,
            'route_name': self.route_name,
            'source': self.source,
            'stop_id': self.stop_id,
        }
