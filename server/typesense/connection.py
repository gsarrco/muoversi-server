import os

import yaml
from typesense import Client


def connect_to_typesense():
    parent_of_parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
    config_path = os.path.join(parent_of_parent_dir, 'config.yaml')
    with open(config_path, 'r') as config_file:
        config = yaml.safe_load(config_file)
    return Client({
        'api_key': config['TYPESENSE_API_KEY'],
        'nodes': [{
            'host': config.get('TYPESENSE_HOST', 'localhost'),
            'port': '8108',
            'protocol': 'http'
        }],
        'connection_timeout_seconds': 2
    })
