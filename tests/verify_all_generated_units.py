"""Compile every generated board translation unit without publishing SDK outputs."""
from pathlib import Path
import sys,json,subprocess,xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
TOOL=Path(__file__).resolve().parents[1];board=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else TOOL/'.reports/code-review-20261020';state=TOOL/'.reports/full-board-compile';state.mkdir(exist_ok=True)
compiler=Path('D:/Keil/ARM/ARMCC/bin/armcc.exe');jobs=[]
for project in sorted(board.glob('build/*/brd.uvprojx')):
 xml=ET.parse(project).getroot();target=project.parent.name
 includes=[str((project.parent/entry.replace(chr(92),'/')).resolve()) for n in xml.iter('IncludePath') for entry in (n.text or '').split(';') if entry]
 defines=[v.strip() for n in xml.iter('Define') for v in (n.text or '').split(',') if v.strip()]
 for n in xml.iter('FilePath'):
  file=(project.parent/n.text.replace(chr(92),'/')).resolve()
  if board.resolve() not in file.parents or file.suffix!='.c':continue
  args=[str(compiler),'--cpu=Cortex-M4','--c99','-c',str(file),'-o',str(state/(target+'-'+file.stem+'.o'))]
  for v in defines:args+=['-D'+v]
  for include in includes:args+=['-I',include]
  jobs.append((target,file,args))
def run(job):
 target,file,args=job;r=subprocess.run(args,capture_output=True,text=True);message=r.stdout+r.stderr
 return {'target':target,'file':file.relative_to(board).as_posix(),'exit_code':r.returncode,'diagnostics':message}
with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(run,jobs))
(TOOL/'.reports/all-generated-units-compile.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for r in results:
 if r['exit_code'] or r['diagnostics']:print(r['file'],r['exit_code'],r['diagnostics'][-2000:])
print('Generated translation units:',len(results),'passed:',sum(r['exit_code']==0 for r in results))
assert results and all(r['exit_code']==0 for r in results),'Generated source compilation failed'
