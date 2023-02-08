import logging
import os
import re
import sqlite3
import subprocess
import urllib
from datetime import datetime
import ssl
from sqlite3 import Connection

import requests
from bs4 import BeautifulSoup
import urllib.request


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

def get_latest_gtfs_version(transport_type):
    url = f"https://actv.avmspa.it/sites/default/files/attachments/opendata/{transport_type}/"

    response = requests.get(url)

    soup = BeautifulSoup(response.text, "html.parser")

    link = soup.find_all("a")[-1]
    filename = link.get('href')
    match = re.search(r'\d+', filename)
    version = int(match.group(0))
    # datetime_str = str(link.next_sibling).strip().split('            ')[0]
    # datetime_obj = datetime.strptime(datetime_str, '%d-%b-%Y %H:%M')
    return version


class DBFile:
    def __init__(self, transport_type, gtfs_version=None):
        self.transport_type = transport_type

        if not gtfs_version:
            gtfs_version = get_latest_gtfs_version(transport_type)

        for try_version in range(gtfs_version, 0, -1):
            self.gtfs_version = try_version
            self.download_and_convert_file()
            if self.get_calendar_services():
                break

    def file_path(self, ext):
        current_dir = os.path.abspath(os.path.dirname(__file__))
        parent_dir = os.path.abspath(current_dir + "/../")

        return os.path.join(parent_dir, f'{self.transport_type}_{self.gtfs_version}.{ext}')

    def download_and_convert_file(self, force=False):
        if not os.path.isfile(self.file_path('zip')) or force:
            url = f'https://actv.avmspa.it/sites/default/files/attachments/opendata/' \
                  f'{self.transport_type}/actv_{self.transport_type[:3]}_{self.gtfs_version}.zip'
            ssl._create_default_https_context = ssl._create_unverified_context
            file_path = self.file_path('zip')
            logger.info('Downloading %s to %s', url, file_path)
            urllib.request.urlretrieve(url, file_path)

        if not os.path.isfile(self.file_path('db')) or force:
            subprocess.run(["gtfs-import", "--gtfsPath", self.file_path('zip'), '--sqlitePath', self.file_path('db')])

    def get_calendar_services(self) -> list[str]:
        today_ymd = datetime.today().strftime('%Y%m%d')
        weekday = datetime.today().strftime('%A').lower()
        with sqlite3.connect(self.file_path('db')) as con:
            cur = con.cursor()

            services = cur.execute(
                f'SELECT service_id FROM calendar WHERE {weekday} = 1 AND start_date <= ? AND end_date >= ?',
                (today_ymd, today_ymd))

            return list(set([service[0] for service in services.fetchall()]))

    def connect_to_database(self) -> Connection:
        return sqlite3.connect(self.file_path('db'))
