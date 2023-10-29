from datetime import date, datetime
from typing import Optional

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import declarative_base, Mapped, mapped_column, relationship

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
