from server.sources import sources


def run():
    for source in sources.values():
        source.sync_stations_typesense(source.get_source_stations())


if __name__ == '__main__':
    run()
