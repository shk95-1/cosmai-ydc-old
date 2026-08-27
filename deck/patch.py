import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
mod = __import__(sys.argv[1])
part = getattr(mod, sys.argv[2])
p = Path("build.py")
s = p.read_text(encoding="utf-8")
tail = 'prs.save(OUT)\nprint("\u2192", OUT)'
assert tail in s, "꼬리표를 못 찾았다"
s = s.replace(tail, part.strip() + "\n\n\n" + tail)
p.write_text(s, encoding="utf-8")
print("patched", sys.argv[2])
