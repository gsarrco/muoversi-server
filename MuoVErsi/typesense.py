import os

import yaml
from typesense import Client


def connect_to_typesense():
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(parent_dir, 'config.yaml')
    with open(config_path, 'r') as config_file:
        config = yaml.safe_load(config_file)
    return Client({
        'api_key': config['TYPESENSE_API_KEY'],
        'nodes': [{
            'host': 'localhost',
            'port': '8108',
            'protocol': 'http'
        }],
        'connection_timeout_seconds': 2
    })
