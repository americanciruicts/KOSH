"""Shared target-database resolution for the KOSH acceptance suites.

WHY THIS EXISTS: acceptance_app/_b/_extra COMMIT real movements (they drive the real
stock_pcb / pick_pcb / restock_pcb, which commit).  They were originally pinned to a
scratch DB named `kosh_rebuild` so they could never touch production.  That DB was
later dropped, which silently killed all three suites — the same rot that had
regression_tests.py pointing at the long-renamed `pcb_inventory` schema (2026-07-15).

So the pin is REPLACED, not removed: the target is now configurable but PRODUCTION IS
REFUSED OUTRIGHT.  A test suite that commits must never be one env var away from
writing to `kosh`.
"""
import os
import sys

PROD_DBS = {'kosh'}
DEFAULT_DB = 'kosh_test'


def target_db():
    """Return the DB these suites may write to, or exit rather than touch prod."""
    db = os.environ.get('KOSH_TEST_DB') or os.environ.get('POSTGRES_DB') or DEFAULT_DB
    if db in PROD_DBS:
        print(f'REFUSING TO RUN: target database is production ({db!r}). '
              f'These suites COMMIT. Run them against {DEFAULT_DB} instead, e.g. '
              f'KOSH_TEST_DB={DEFAULT_DB} python <suite>.py')
        sys.exit(2)
    return db


def connect(**overrides):
    """psycopg2 connection to the (non-prod) target DB."""
    import psycopg2
    params = dict(
        host=os.environ.get('POSTGRES_HOST', 'aci-database'),
        dbname=target_db(),
        user=os.environ.get('POSTGRES_USER', 'aci'),
        password=os.environ.get('POSTGRES_PASSWORD'),
    )
    params.update(overrides)
    return psycopg2.connect(**params)
