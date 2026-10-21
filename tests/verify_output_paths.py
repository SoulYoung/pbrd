"""Output location regression: reserved names, nesting, paths and update protection."""
from pathlib import Path
import sys,json,tempfile,xml.etree.ElementTree as ET
TOOL=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(TOOL),str(TOOL/'ui')]
from project_context import project_context
from generator.engine import generate_project
ctx=project_context();defaults=json.loads((TOOL/'platforms/ac78428-defaults.json').read_text(encoding='utf-8-sig'))
config={'format':'pbrd-project','schema_version':1,'ui_schema_version':2,'project':{'model':'PATH_VERIFY','revision':'R01V01','product_enum':'kBrd_VersionTxj_br4_cx20p','date':'2026-10-20','author':''},'platform':{'mcu':'ac78428'},'build':{'adapter':'keil','version':'5.23'},'targets':{'app':{'requested':['brd.common','brd.clock','drv.common','drv.clock','drv.gpio','drv.irq','drv.port'],'disabled':[],'touched':[]}},'board':{'modules':{},'buses':[]},'codegen':{'adapter':defaults['adapter'],'parameters':defaults['parameters']},'output':{'mode':'create','compare_to':''}}
(ctx['tool_root']/'.reports').mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix='output-path-check-',dir=ctx['tool_root']/'.reports') as temporary:
 base=Path(temporary)
 for target in [base/'deep'/'r01v01',base/'another'/'custom-board']:
  config['output']['mode']='create';report=generate_project(ctx,config,target)
  project=target/'build/ac78428/brd.uvprojx';assert project.is_file()
  xml=ET.parse(project).getroot()
  for node in xml.iter('FilePath'):
   resolved=(project.parent/node.text.replace('\\','/')).resolve();assert resolved.is_file(),resolved
  includes=[entry for n in xml.iter('IncludePath') for entry in (n.text or '').split(';')]
  assert any((project.parent/e.replace('\\','/')).resolve()==ctx['project_root']/'product/src/brd/base/inc' for e in includes)
  assert any((project.parent/e.replace('\\','/')).resolve()==target/'ac78428/def' for e in includes)
  script=(project.parent/'after_build.bat').read_text(encoding='utf-8')
  assert '%~dp0..\\..\\..\\%AFTER_BUILD_CHIP_NO_IAR%' not in script
  try:generate_project(ctx,config,target)
  except ValueError as e:assert 'Output exists' in str(e),str(e)
  else:raise AssertionError('Create mode overwrote existing directory')
  config['output']['mode']='regenerate';generate_project(ctx,config,target)
  print('PASS new/regenerate, Keil source/include paths and shared script:',target.name)
print('PASS output path checks; no compiler invoked')
