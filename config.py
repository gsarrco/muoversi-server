import logging
import os

import yaml

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

current_dir = os.path.abspath(os.path.dirname(__file__))

config_path = os.path.join(current_dir, 'config.yaml')
with open(config_path, 'r') as config_file:
    try:
        config = yaml.safe_load(config_file)
        logger.info(config)
    except yaml.YAMLError as err:
        logger.error(err)
