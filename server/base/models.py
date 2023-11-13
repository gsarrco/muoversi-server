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


class PartitionByOrigDepDateMeta(DeclarativeMeta):
    def __new__(cls, clsname, bases, attrs, *, partition_by):
        @classmethod
        def get_partition_name(cls_, key):
            return f'{cls_.__tablename__}_{key}'

        @classmethod
        def create_partition(cls_, day: date):
            key = day.strftime('%Y%m%d')
            if key not in cls_.partitions:
                Partition = type(
                    f'{clsname}{key}',
                    bases,
                    {'__tablename__': cls_.get_partition_name(key)}
                )

                Partition.__table__.add_is_dependent_on(cls_.__table__)

                day_plus_one = day + timedelta(days=1)
                event.listen(
                    Partition.__table__,
                    'after_create',
                    DDL(
                        f"""
                        ALTER TABLE {cls_.__tablename__}
                        ATTACH PARTITION {Partition.__tablename__}
                        FOR VALUES FROM ('{day}') TO ('{day_plus_one}')
                        """
                    )
                )

                cls_.partitions[key] = Partition

            return cls_.partitions[key]

        attrs.update(
            {
                '__table_args__': attrs.get('__table_args__', ())
                                  + (dict(postgresql_partition_by=f'RANGE({partition_by})'),),
                'partitions': {},
                'partitioned_by': partition_by,
                'get_partition_name': get_partition_name,
                'create_partition': create_partition
            }
        )

        return super().__new__(cls, clsname, bases, attrs)


class StopTimeMixin:
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

    @declared_attr
    def stop_id(self) -> Mapped[str]:
        return mapped_column(ForeignKey('stops.id'))

    @declared_attr
    def stop(self) -> Mapped[Stop]:
        return relationship('Stop', foreign_keys=self.stop_id)


class StopTime(StopTimeMixin, Base, metaclass=PartitionByOrigDepDateMeta, partition_by='orig_dep_date'):
    __tablename__ = 'stop_times'

    __table_args__ = (UniqueConstraint("stop_id", "number", "source", "orig_dep_date"),)
