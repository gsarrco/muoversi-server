from geopy.distance import distance


def get_clusters_of_stops(stops):
    clusters = cluster_strings(stops)
    for cluster_name, stops in clusters.copy().items():
        stops = stops['stops'].copy()
        if len(stops) > 1:
            # calculate centroid of the coordinates
            latitudes = [stop['coords'][0] for stop in stops]
            longitudes = [stop['coords'][1] for stop in stops]
            centroid_lat = sum(latitudes) / len(latitudes)
            centroid_long = sum(longitudes) / len(longitudes)
            centroid = (round(centroid_lat, 7), round(centroid_long, 7))

            split_cluster = False
            for stop in stops:
                if distance(stop['coords'], centroid).m > 200:
                    split_cluster = True
                    break
            if split_cluster:
                del clusters[cluster_name]
                i = 1
                for stop in stops:
                    if stop['stop_name'] in clusters:
                        clusters[f'{stop["stop_name"]} ({i})'] = {'stops': [stop], 'coords': stop['coords'],
                                                                  'times_count': stop['times_count']}
                        i += 1
                    else:
                        clusters[stop['stop_name']] = {'stops': [stop], 'coords': stop['coords'],
                                                       'times_count': stop['times_count']}
            else:
                clusters[cluster_name]['coords'] = centroid
                clusters[cluster_name]['times_count'] = sum(stop['times_count'] for stop in stops)
        else:
            clusters[cluster_name]['coords'] = stops[0]['coords']
            clusters[cluster_name]['times_count'] = stops[0]['times_count']
    return clusters


def cluster_strings(stops):
    stops = [(stop[0], stop[1].upper(), stop[2], stop[3], stop[4]) for stop in stops]
    stops.sort(key=lambda x: x[1])
    longest_prefix = ''
    clusters = {}
    for i1 in range(len(stops)):
        i2 = i1 + 1
        ref_el = stops[i1]
        first_string = ref_el[1]
        second_string = stops[i2][1] if i2 < len(stops) else ''
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
        clusters.setdefault(cluster_name, {'stops': []})['stops'].append(
            {'stop_id': ref_el[0], 'stop_name': first_string, 'coords': (ref_el[2], ref_el[3]),
             'times_count': ref_el[4]})

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
