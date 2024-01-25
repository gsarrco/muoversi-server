import logging

import click

from server.sources import session, sources as all_sources

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


@click.command()
@click.option('--source', '-s', multiple=True, default=[],
              help='Sources to update. Leave empty to update all sources')
def run(source: list[str]):
    session.commit()

    # if a list of sources is specified, only those sources will be updated, otherwise all sources will be updated
    if len(source) > 0:
        sources = {k: v for k, v in all_sources.items() if k in source}
    else:
        sources = all_sources

    for source in sources.values():
        try:
            source.save_data()
        except KeyboardInterrupt:
            session.rollback()


if __name__ == '__main__':
    run()
