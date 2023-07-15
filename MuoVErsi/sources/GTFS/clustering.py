from geopy.distance import distance

from .models import CStop, CCluster


def get_clusters_of_stops(stops: list[CStop]) -> list[CCluster]:
    clusters = cluster_strings(stops)
    for cluster_name, cluster in clusters.copy().items():
        stops = cluster.stops.copy()
        if len(stops) > 1:
            # calculate centroid of the coordinates
            latitudes = [stop.lat for stop in stops]
            longitudes = [stop.lon for stop in stops]
            centroid_lat = sum(latitudes) / len(latitudes)
            centroid_long = sum(longitudes) / len(longitudes)
            centroid = (round(centroid_lat, 7), round(centroid_long, 7))

            split_cluster = False
            for stop in stops:
                stop_coords = (stop.lat, stop.lon)
                if distance(stop_coords, centroid).m > 200:
                    split_cluster = True
                    break
            if split_cluster:
                del clusters[cluster_name]
                i = 1
                for stop in stops:
                    if stop.name in clusters:
                        a_cluster_name = f'{stop.name} ({i})'
                        i += 1
                    else:
                        a_cluster_name = stop.name
                    a_cluster = CCluster(a_cluster_name, [stop], stop.lat, stop.lon, stop.times_count)
                    clusters[a_cluster_name] = a_cluster
            else:
                cluster.lat, cluster.lon = centroid
                cluster.times_count = sum(stop.times_count for stop in stops)
        else:
            cluster.lat, cluster.lon = stops[0].lat, stops[0].lon
            cluster.times_count = stops[0].times_count
    return list(clusters.values())


def cluster_strings(stops: list[CStop]) -> dict[str, CCluster]:
    stops = [CStop(stop.id, stop.name.upper(), stop.lat, stop.lon, stop.times_count) for stop in stops]
    stops.sort(key=lambda stop: stop.name)
    longest_prefix = ''
    clusters: dict[str, CCluster] = {}
    for i1 in range(len(stops)):
        i2 = i1 + 1
        ref_el = stops[i1]
        first_string = ref_el.name
        second_string = stops[i2].name if i2 < len(stops) else ''
        first_string, second_string = first_string.strip().upper(), second_string.strip().upper()
        new_cluster = True
        new_longest_prefix = find_longest_prefix(first_string, second_string).rstrip(' "').rstrip()

        if longest_prefix != '':
            # space = " " if len(first_string.split()) > 1 else ""
            if first_string.startswith(longest_prefix) \
                    and len(new_longest_prefix) <= len(longest_prefix):
                new_cluster = False

        if new_cluster:
            longest_prefix = new_longest_prefix

        cluster_name = longest_prefix if longest_prefix != '' and len(longest_prefix) > (
                len(first_string) / 3) else first_string
        # add_to_cluster(clusters, cluster_name, first_string, stops[i1][2:4])
        cluster = CCluster(cluster_name)
        clusters.setdefault(cluster_name, cluster).stops.append(ref_el)

    return clusters


def find_longest_prefix(str1, str2):
    words1 = str1.split()
    words2 = str2.split()
    prefix = ""
    for i in range(min(len(words1), len(words2))):
        if words1[i] == words2[i]:
            prefix += words1[i] + " "
        else:
            break
    return prefix.strip()


def get_loc_from_stop_and_cluster(stop_name, cluster_name):
    return stop_name.upper().replace(cluster_name.upper(), "").strip()
