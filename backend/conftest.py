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
