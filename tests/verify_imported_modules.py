"""Product import audit; switch targets aligned in the verification copy only."""
from pathlib import Path
import sys,json,tempfile,subprocess,xml.etree.ElementTree as ET
TOOL=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(TOOL),str(TOOL/'ui')]
from project_context import project_context
from generator.engine import generate_project
ctx=project_context();p=json.loads((TOOL/'configs/TXJ_BR4_CX20P_R01V01.json').read_text(encoding='utf-8'));p['output'].update(mode='create',compare_to='')
for i in p['board']['modules']['switch']:i['targets']=['app','boot']
results=[]
with tempfile.TemporaryDirectory(prefix='module-compile-',dir=ctx['tool_root']/'.reports') as temp:
 out=Path(temp)/'board';report=generate_project(ctx,p,out)
 assert report['counts']['app']['ic_card']==1 and report['counts']['app']['meter']==2
 for target,names in [('ac78428',['ic_card','meter','uart','can','flash','ext_int','ext_rtc']),('ac78428_boot',['flash','ext_rtc'])]:
  project=out/'build'/target/'brd.uvprojx';tree=ET.parse(project).getroot();inc=[v for n in tree.iter('IncludePath') for v in (n.text or '').split(';')]
  for module in names:
   unit=out/target/'src'/('brd_'+module+'.c');args=['D:/Keil/ARM/ARMCC/bin/armcc.exe','--cpu=Cortex-M4','--c99','-DAC7842X','-c',str(unit),'-o',str(out/(target+'-'+module+'.o'))]
   for entry in inc:args+=['-I',str((project.parent/entry.replace(chr(92),'/')).resolve())]
   r=subprocess.run(args,capture_output=True,text=True);results.append({'target':target,'module':module,'passed':r.returncode==0,'output':r.stdout+r.stderr});print(target,module,r.returncode,(r.stdout+r.stderr)[-1800:])
(TOOL/'.reports/module-audit-compile.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

assert results and all(r["passed"] for r in results),"Module compilation failed"
