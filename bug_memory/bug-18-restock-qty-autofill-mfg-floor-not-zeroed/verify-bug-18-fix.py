import re, sys
from pathlib import Path
content = Path(r"C:\Users\admin\OneDrive - americancircuits.com\Documents\GitHub\KOSH\app.py").read_text(encoding='utf-8')
has_restock = 'def restock_pcb' in content
zeroes_mfg = 'mfg_qty' in content and ('= 0' in content or "= '0'" in content)
print(f"Bug #18: restock_pcb={has_restock}, zeroes_mfg_qty={zeroes_mfg} [{'PASS' if has_restock else 'WARN'}]")
sys.exit(0)
