#! .\SportsbookOdds\env\Scripts\python.exe

import os
from dotenv import load_dotenv

# Get the directory of this config file, then go up to the project root
config_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(config_dir)

API_DATA_DIR = os.path.join(project_root, 'data', 'API', 'key.env')
ODDS_RAW_DATA_DIR = os.path.join(project_root, 'data', 'raw')

# API Key(s)
load_dotenv(API_DATA_DIR)
THEODDSAPI_KEY_TEST = os.getenv('THEODDSAPI_KEY_TEST')
THEODDSAPI_KEY_PROD = os.getenv('THEODDSAPI_KEY_PROD')

ODDS_FORMAT = 'decimal'

PALETTES = {
    'dark': {
        'background-dark': '#212121',
        'table-hdr-dark': '#27374d',
        'combobox-hover': '#0f4c75',
        'table-row-alt1': '#222831',
        'table-row-alt2': '#393e46',
        'table-row-hover': '#6096b4',
        'text-light': '#eeeeee',
        'text-dark': '#000000'
    },
    'light': {
        'background-dark': '#F9F7F7',
        'table-hdr-dark': '#B1B2FF',
        'combobox-hover': '#AAC4FF',
        'table-row-alt1': '#D2DAFF',
        'table-row-alt2': '#EEF1FF',
        'table-row-hover': '#A6B1E1',
        'text-light': '#000000',
        'text-dark': '#222831'
    }
}

PALETTE = PALETTES['dark']