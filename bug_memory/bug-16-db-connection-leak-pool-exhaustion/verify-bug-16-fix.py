import re, sys
from pathlib import Path
content = (Path(__file__).resolve().parents[2] / "app.py").read_text(encoding='utf-8')
has_return_conn = 'def return_connection' in content
has_close = 'close()' in content or '.close()' in content
print(f"Bug #16: return_connection={has_return_conn}, close={has_close} [{'PASS' if has_return_conn and has_close else 'FAIL'}]")
sys.exit(0 if (has_return_conn and has_close) else 1)
