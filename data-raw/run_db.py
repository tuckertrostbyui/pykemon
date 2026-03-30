"""
This will be the standalone script that will eventually reset db and tables
"""

import duckdb
import sys

sys.path.insert(0, "data-raw")

from build_db import make_db, insert_pokemon

DB_PATH = "src/pykemon/data/pykemon.duckdb"

con = duckdb.connect(DB_PATH)
make_db(con)
con.close()
print("Done")
