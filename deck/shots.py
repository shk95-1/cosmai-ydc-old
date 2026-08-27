"""PowerPoint 로 슬라이드를 PNG 로 내보낸다. 넘침·겹침은 눈으로 봐야 잡힌다."""
import sys, os
from pathlib import Path
import win32com.client

src = Path(r'C:\Users\Admin\Downloads\[1팀_리메릭]발표자료_260827_COSMAI.pptx')
out = Path(sys.argv[1] if len(sys.argv) > 1 else r'C:\Users\Admin\AppData\Local\Temp\claude\shots')
out.mkdir(parents=True, exist_ok=True)
for f in out.glob("*.png"):
    f.unlink()

app = win32com.client.Dispatch("PowerPoint.Application")
pres = app.Presentations.Open(str(src), WithWindow=False)
try:
    for i, sl in enumerate(pres.Slides, 1):
        sl.Export(str(out / f"{i:02d}.png"), "PNG", 1600, 900)
    print(f"{pres.Slides.Count}장 → {out}")
finally:
    pres.Close()
    app.Quit()
