"""
This file is for the functions to connect to the db.
"""

import duckdb
from importlib.resources import files


def get_connection():
    path = files("pykemon.data").joinpath("pykemon.duckdb")
    return duckdb.connect(str(path), read_only=True)
