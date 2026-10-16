"""Strict explicit placeholders; never interpret ordinary C braces."""
from pathlib import Path
import re
TOKEN=re.compile(r'\{\{([A-Z][A-Z0-9_]*)\}\}')
def render(source,values):
    needed=set(TOKEN.findall(source));missing=needed-set(values);unused=set(values)-needed
    if missing or unused:raise ValueError('Template context mismatch; missing='+str(sorted(missing))+' unused='+str(sorted(unused)))
    return TOKEN.sub(lambda match:str(values[match[1]]),source)
def render_file(path,values):return render(Path(path).read_text(encoding='utf-8-sig'),values)
