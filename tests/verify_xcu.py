"""App XCU source comparison, project generation and optional ARMCC smoke check."""
from pathlib import Path
import sys,json,tempfile,traceback,subprocess,xml.etree.ElementTree as ET
TOOL=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(TOOL),str(TOOL/'ui')]
from project_context import project_context
from generator.engine import generate_project
from generator.modules.additional import xcu
from generator.c_parser import declarations
ctx=project_context();p=json.loads((TOOL/'configs/TXJ_BR4_CX20P_R01V01.json').read_text(encoding='utf-8-sig'));platform=json.loads((TOOL/'platforms/ac78428.json').read_text(encoding='utf-8-sig'))
code=xcu(p['board']['modules']['xcu'],platform);assert '{{' not in code
values={d['name']:d['value'] for d in declarations(code)}
assert values['g_drv_xcu_spi_cfg']==p['codegen']['parameters']['ac78428/cfg/brd_xcu_cfg.c']['values']['g_drv_xcu_spi_cfg']
print('PASS XCU SPI configuration matches original source')
# Exercise XCU with only its foundations to isolate the module from unrelated import limitations.
p['targets']={'app':{'requested':['brd.common','brd.clock','brd.xcu','drv.common','drv.clock','drv.gpio','drv.irq','drv.port'],'disabled':[],'touched':[]}};p['output'].update(mode='create',compare_to='')
with tempfile.TemporaryDirectory(prefix='xcu-check-',dir=ctx['tool_root']/'.reports') as tmp:
 out=Path(tmp)/'custom-output'
 try:
  report=generate_project(ctx,p,out);print('PASS XCU project generation',report['counts'])
  project=out/'build/ac78428/brd.uvprojx';xml=ET.parse(project).getroot();inc=[entry for n in xml.iter('IncludePath') for entry in (n.text or '').split(';')]
  compiler=Path('D:/Keil/ARM/ARMCC/bin/armcc.exe')
  for n,unit in enumerate([out/'ac78428/src/brd_xcu.c',ctx['project_root']/'product/src/hal/xcu/common/xcu.c',ctx['project_root']/'product/src/hal/xcu/common/xcu_net.c']):
   if not compiler.is_file():
    print('SKIP ARMCC unavailable');break
   args=[str(compiler),'--cpu=Cortex-M4','--c99','-DAC7842X','-c',str(unit),'-o',str(out/('check'+str(n)+'.o'))]
   for entry in inc:args+=['-I',str((project.parent/entry.replace(chr(92),'/')).resolve())]
   result=subprocess.run(args,capture_output=True,text=True)
   print(unit.name,result.returncode,result.stdout,result.stderr)
   assert result.returncode==0,'XCU ARMCC compile failed'
  import copy
  changed=copy.deepcopy(p['board']['modules']['xcu']);changed[0]['params']['stack_size']=1024
  assert 'stack[2][1024]' in xcu(changed,platform)
  for invalid in [[],changed+changed]:
   try:xcu(invalid,platform)
   except ValueError:pass
   else:raise AssertionError('Singleton validation failed')
  print('PASS stack mapping and singleton validation')
 except Exception:traceback.print_exc();raise
