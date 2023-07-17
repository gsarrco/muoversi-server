import pandas as pd
from geopy.distance import distance
from tqdm import tqdm

tqdm.pandas()

df = pd.read_csv('https://raw.githubusercontent.com/trainline-eu/stations/master/stations.csv', sep=';',
                 usecols=['name', 'latitude', 'longitude', 'country', 'trenitalia_rtvt_id'])
df = df.query('country == "IT" & trenitalia_rtvt_id.notnull() & latitude.notnull() & longitude.notnull()')
santa_lucia_coords = 45.441569, 12.320882

# filter out stations that are more than 110km away from Santa Lucia
df['distance'] = df.progress_apply(lambda row: distance(santa_lucia_coords, (row['latitude'], row['longitude'])).km,
                                   axis=1)
df = df.query('distance < 110')

df = df[['name', 'latitude', 'longitude', 'trenitalia_rtvt_id']]

df.columns = ['long_name', 'latitude', 'longitude', 'code']

df.to_json('MuoVErsi/sources/data/trenitalia_stations.json', orient='records', indent=2)
