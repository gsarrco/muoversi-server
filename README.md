# Muoversi Server

MuoVErsi is a web service that parses and serves timetables of buses, trams, trains and waterbusses. As of now, it
supports Venice, Italy's public transit system (by using public GTFS files) and Trenitalia trains within 100km from
Venice (parsed from the Trenitalia api). However, since it can build on any GTFS file, it will be easily extended to
other cities in the future.

Separated from the core code and optional to set up, a Telegram bot uses the web service to provide a more user-friendly
interface. You can check it out here: [@MuoVErsiBot](https://t.me/MuoVErsiBot). **Also, the mobile app for Android and iOS is under active development: [muoversi-app](https://github.com/gsarrco/muoversi-app)**.

## Features

MuoVErsi allows you to get departure times from a given stop or location, or starting from a specific line. You can then
use filters to get the right results and see all the stops/times of that specific route.

When new data is parsed and saved to the database, stops are not simply stored as-is, but they are clustered
by name and location. This way it is easier to search for bus stations with more than one bus stop. For example,
"Piazzale Roma" has 15 different bus stops from the GTFS file, but they are all clustered together.

## Installation

### Requirements

- Python 3
- PostgreSQL 16.1 for the database
- Packages contained in `requirements.txt`
- [node-gtfs](https://github.com/blinktaginc/node-gtfs) installed globally
- [Typesense](https://typesense.org/) for the stop search engine
- [Telegram bot token](https://core.telegram.org/bots/features#botfather) if you also want to run the bot

### Steps

1. Download the repo and install the dependencies with `pip install -r requirements.txt`.
2. Fill out the config file `config.example.yaml` and rename it to `config.yaml`. If you don't want to run the Telegram,
   bot, set `TG_BOT_ENABLED` to `False` and skip the all the variables starting with `TG_`. You won't need the `tgbot`
   folder.
3. Run PostgreSQL migrations with `alembic upgrade head`.
4. Run the server by executing `run.py`. For saving data from the GTFS files and, more importantly, for the parsing and
   saving of Trenitalia trains, make sure you schedule the execution of `save_data.py` once a day. As of now, also
   a daily restart of `run.py` is required to set the service calendar to the current day.
