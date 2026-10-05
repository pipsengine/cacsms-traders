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
    # Cloud deployment binds to the public interface; localhost remains development-only.
    host = os.getenv("APP_HOST", "0.0.0.0").strip() or "0.0.0.0"
    port = int(os.getenv("APP_PORT", "8000"))
    reload = os.getenv("API_RELOAD", "0").strip() in ("1", "true", "yes")
    uvicorn.run("apps.api.app.main:app", host=host, port=port, reload=reload)
