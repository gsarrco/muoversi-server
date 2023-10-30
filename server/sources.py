from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import config
from server.GTFS import GTFS
from server.trenitalia import Trenitalia
from server.typesense import connect_to_typesense

engine_url = f"postgresql://{config['PGUSER']}:{config['PGPASSWORD']}@{config['PGHOST']}:{config['PGPORT']}/" \
             f"{config['PGDATABASE']}"
engine = create_engine(engine_url)

session = sessionmaker(bind=engine)()
typesense = connect_to_typesense()

sources = {
    'aut': GTFS('automobilistico', '🚌', session, typesense, dev=config.get('DEV', False)),
    'nav': GTFS('navigazione', '⛴️', session, typesense, dev=config.get('DEV', False)),
    'treni': Trenitalia(session, typesense)
}

for source in sources.values():
    source.sync_stations_typesense(source.get_source_stations())
