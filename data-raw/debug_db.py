from build_db import print_schema
import duckdb

DB_PATH = "src/pykemon/data/pykemon.duckdb"

con = duckdb.connect(DB_PATH, read_only=True)

print_schema(con)
