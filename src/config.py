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

ODDS_FORMAT = 'american'

PALETTES = {
    'dark': {
        'background-dark': '#0F172A',
        'table-hdr-dark': '#1E293B',
        'combobox-hover': '#1D4ED8',
        'table-row-alt1': '#111827',
        'table-row-alt2': '#1F2937',
        'table-row-hover': '#2563EB',
        'text-light': '#E5E7EB',
        'text-dark': '#0B1220'
    },
    'light': {
        'background-dark': '#F8FAFC',
        'table-hdr-dark': '#E2E8F0',
        'combobox-hover': '#93C5FD',
        'table-row-alt1': '#F1F5F9',
        'table-row-alt2': '#E2E8F0',
        'table-row-hover': '#BFDBFE',
        'text-light': '#0F172A',
        'text-dark': '#1E293B'
    }
}

PALETTE = PALETTES['dark']
