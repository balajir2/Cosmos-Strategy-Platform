import os
import sys

BACKEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Several test modules do os.environ.setdefault("DATABASE_URL", "postgresql://test/test")
# at their own top level, as a harmless placeholder for tests that fully mock the DB
# layer. But pytest imports every test module during collection before running any
# test, so whichever module happens to be collected first "wins" that setdefault - and
# since dotenv.load_dotenv() never overrides an already-set var, database.py's own
# load_dotenv() call (on first import) then does nothing, leaving every test for the
# rest of the process stuck on the fake DSN. Loading the real .env here, in conftest.py
# (always imported before any test module in its directory), lets the real DATABASE_URL
# win that race instead, matching Quick Start's documented "requires a reachable
# DATABASE_URL" behavior for the suite as a whole.
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(BACKEND_DIR), ".env"))
