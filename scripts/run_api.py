import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.app.core.env_loader import load_env_file

load_env_file()

import uvicorn

if __name__ == "__main__":
    # Off by default: on Windows the reloader's Ctrl+C reaches the whole console group and
    # `concurrently -k` then stops the web dev server too.
    reload = os.getenv("API_RELOAD", "0").strip() in ("1", "true", "yes")
    uvicorn.run("apps.api.app.main:app", host="127.0.0.1", port=8000, reload=reload)
