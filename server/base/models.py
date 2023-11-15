from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import ForeignKey, UniqueConstraint, event
from sqlalchemy.ext.declarative import DeclarativeMeta
from sqlalchemy.orm import declarative_base, Mapped, mapped_column, relationship, declared_attr
from sqlalchemy.sql.ddl import DDL

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
    active: Mapped[bool] = mapped_column(server_default='true')

    def as_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'lat': self.lat,
            'lon': self.lon,
            'source': self.source
        }


class Stop(Base):
    __tablename__ = 'stops'

    id: Mapped[str] = mapped_column(primary_key=True)
    platform: Mapped[Optional[str]]
    lat: Mapped[float]
    lon: Mapped[float]
    station_id: Mapped[str] = mapped_column(ForeignKey('stations.id'))
    station: Mapped[Station] = relationship('Station', back_populates='stops')
    source: Mapped[Optional[str]]
    active: Mapped[bool] = mapped_column(server_default='true')


class StopTime(Base):
    __tablename__ = 'stop_times'

    id: Mapped[int] = mapped_column(primary_key=True)
    sched_arr_dt: Mapped[Optional[datetime]]
    sched_dep_dt: Mapped[Optional[datetime]]
    orig_dep_date: Mapped[date]
    platform: Mapped[Optional[str]]
    orig_id: Mapped[str]
    dest_text: Mapped[str]
    number: Mapped[int]
    route_name: Mapped[str]
    source: Mapped[str] = mapped_column(server_default='treni')
    stop_id: Mapped[str] = mapped_column(ForeignKey('stops.id'))
    stop: Mapped[Stop] = relationship('Stop', foreign_keys=stop_id)
    
    __table_args__ = (UniqueConstraint("stop_id", "number", "source", "orig_dep_date"),)
