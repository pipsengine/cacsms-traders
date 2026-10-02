import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from apps.api.app.services.bootstrap import bootstrap
if __name__=='__main__': bootstrap(); print('Cacsms-Traders database initialized.')
