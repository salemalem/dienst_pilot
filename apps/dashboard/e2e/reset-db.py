"""Drop every schema of the e2e database so the migrations and the seed start from nothing.

Test infrastructure only. `alembic downgrade base` is not used because the downgrade steps do not
accept rows the e2e run itself created (for example approved swaps).
"""

import sys

import psycopg

url = sys.argv[1].replace("postgresql+psycopg://", "postgresql://")
with psycopg.connect(url, autocommit=True) as conn:
    rows = conn.execute(
        "SELECT nspname FROM pg_namespace WHERE nspname !~ '^pg_' AND nspname <> 'information_schema'"
    ).fetchall()
    for (name,) in rows:
        conn.execute(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')
    conn.execute("CREATE SCHEMA public")
