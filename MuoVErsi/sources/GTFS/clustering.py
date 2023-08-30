import re

from .models import CStop, CCluster


def get_clusters_of_stops(stops: list[CStop]) -> list[CCluster]:
    clusters: dict[str, CCluster] = {}
    for stop in stops:
        cluster_name = get_root_from_stop_name(stop.name)
        cluster = clusters.setdefault(cluster_name.upper(), CCluster(cluster_name))
        cluster.stops.append(stop)
        cluster.times_count += stop.times_count
        cluster.lat, cluster.lon = compute_centroid(cluster.stops)
    return list(clusters.values())


def get_root_from_stop_name(stop_name):
    if '"' in stop_name:
        match = re.match(r'([^"]*) ?"[A-Z][0-9]?"$', stop_name)
    else:
        match = re.match(r'([^"]*) [A-Z][0-9]?$', stop_name)
    if match:
        result = match.group(1)
        result = result.rstrip()
        suffixes_to_remove = [' CORSIA', ' P.tta']
        for suffix in suffixes_to_remove:
            result = result.removesuffix(suffix)
    else:
        result = stop_name

    replacements = {
        'Piazzale Roma': 'Piazzale Roma People Mover',
        'VENEZIA': 'VENEZIA Piazzale Roma',
    }

    if result in replacements:
        return replacements[result]

    result = result.replace('Favretti MESTRE FS', 'Stazione MESTRE FS')
    result = result.replace('San ', 'S. ')

    return result


def compute_centroid(stops):
    latitudes = [stop.lat for stop in stops]
    longitudes = [stop.lon for stop in stops]
    centroid_lat = sum(latitudes) / len(latitudes)
    centroid_long = sum(longitudes) / len(longitudes)
    centroid = (round(centroid_lat, 7), round(centroid_long, 7))
    return centroid


def get_loc_from_stop_and_cluster(stop_name, cluster_name):
    stop_name = stop_name.replace('"', '')
    match = re.match(r'.* ([A-Z][0-9]?)$', stop_name)
    if match:
        return match.group(1)
    return ''
