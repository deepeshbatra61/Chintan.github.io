"""Makes `import brief` work from the tests directory.

Kept deliberately empty of fixtures. `brief.py` imports only the standard
library, so tests need no database, no environment variables and no API key.
Note that `import server` still cannot work here: server.py reads
os.environ['MONGO_URL'] at module scope, which is exactly why the brief logic
was moved out of it.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# mongomock applies TTL indexes against the REAL clock, while our tests run on
# fixed dates (e.g. 1 Oct 2026). Once real time passed a fixture's expires_at,
# mongomock silently deleted it and 18 push tests failed on 4 Oct for no code
# reason. Pin mongomock's "now" before every fixture date so TTLs never fire in
# tests (no test relies on TTL deletion; that's Mongo's job in production).
try:
    from datetime import datetime as _dt

    import mongomock as _mongomock

    _mongomock.utcnow = lambda: _dt(2026, 1, 1)
except ImportError:  # the pure-logic tests run without mongomock
    pass
