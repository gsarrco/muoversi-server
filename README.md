MuoVErsi is a Telegram bot for advanced users of Venice, Italy's public transit. You can check it out
here: [@MuoVErsiBot](https://t.me/MuoVErsiBot).

It allows you to get departure times for the next buses, trams and vaporetti (waterbusses) from a given stop or
location, or starting from a specific line. You can then use filters to get the right results and see all the
stops/times of that specific route.

Unfortunately the bot is currently only available in Italian, but I'm working on a translation.

## Infrastructure

The bot is written in Python 3 and uses
the [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) library, both for interacting with
Telegram bot API and for the http server.
The program downloads the data from Venice transit agency Actv's GTFS files and stores it in SQLite databases, thanks to
the
[gtfs](https://www.npmjs.com/package/gtfs) CLI. New data is checked every time the
server service restarts, or every night at 4:00 AM with a cronjob.

When new data arrives, stops are not simply stored in the database, but they are clustered by name and location. This
way it is easier to search for bus stations with more than one bus stop. For example, "Piazzale Roma" has 15
different bus stops from the GTFS file, but they are all clustered together.

The code is not written specifically for Venice, so it can be easily adapted to other cities that use GTFS files.

