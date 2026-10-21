"""Regression for counts, CAN power/FD, RTC naming and Flash source semantics."""
from pathlib import Path
import copy,json,re,sys,tempfile,subprocess,xml.etree.ElementTree as ET
TOOL=Path(__file__).resolve().parents[1];sys.path[:0]=[str(TOOL),str(TOOL/'ui')]
from project_context import project_context
from generator.engine import generate_project
from generator.c_parser import declarations
from generator.modules.additional import ext_rtc,ic_card
from generator.modules.builtins import can_power
ctx=project_context();config=json.loads((TOOL/'configs/TXJ_BR4_CX20P_R01V01.json').read_text(encoding='utf-8'));platform=json.loads((TOOL/'platforms/ac78428.json').read_text(encoding='utf-8'));compiler=Path('D:/Keil/ARM/ARMCC/bin/armcc.exe')
config['output'].update(mode='create',compare_to='r01v02');config['project']['author']='  '
# The user added an App-only switch. Align only this test copy for the shared adapter.
for item in config['board']['modules']['switch']:item['targets']=['app','boot']
def parse(path):
 run=subprocess.run([str(compiler),'-E',str(path)],capture_output=True,check=True)
 return {d['name']:d['value'] for d in declarations(run.stdout.decode('utf-8-sig'))}
def deref(values,ref):
 m=re.fullmatch(r'&(\w+)(?:\[(\d+)\])?',ref);value=values[m[1]]
 return value[int(m[2])] if m[2] is not None else value
def numeric(value):
 if isinstance(value,dict):return {k:numeric(v) for k,v in value.items()}
 if isinstance(value,list):return [numeric(v) for v in value]
 if isinstance(value,str) and re.fullmatch(r'(?:0x[0-9a-fA-F]+|\d+)[uUlL]*',value):return int(re.sub(r'[uUlL]+$','',value),0)
 return value
def compile_can(board):
 project=board/'build/ac78428/brd.uvprojx';xml=ET.parse(project).getroot();args=[str(compiler),'--cpu=Cortex-M4','--c99','-DAC7842X','-c',str(board/'ac78428/src/brd_can.c'),'-o',str(board/'can.o')]
 for n in xml.iter('IncludePath'):
  for entry in (n.text or '').split(';'):
   if entry:args+=['-I',str((project.parent/entry.replace(chr(92),'/')).resolve())]
 run=subprocess.run(args,capture_output=True,text=True);assert run.returncode==0,run.stdout+run.stderr
with tempfile.TemporaryDirectory(prefix='code-quality-',dir=TOOL/'.reports') as temp:
 board=Path(temp)/'no-fd';generate_project(ctx,config,board)
 files={p.relative_to(board).as_posix():p.read_text(encoding='utf-8') for p in board.rglob('*') if p.suffix in ['.c','.h']}
 assert not any('brd_canfd_def.h' in k or 'brd_ext_rtc_def.h' in k for k in files)
 assert not any('#include "brd_canfd' in v or '#include "brd_ext_rtc_def' in v for v in files.values()),[k for k,v in files.items() if '#include "brd_canfd' in v or '#include "brd_ext_rtc_def' in v]
 assert not any(re.search(r'\.count\s*=\s*[1-9]\d*\s*,',v) for v in files.values())
 can=files['ac78428/cfg/brd_can_cfg.c'];assert 'Brd_CanDoPowerSupply' in can
 assert 'Brd_CanBusNo(handle) == kBrd_CanId1' in can and 'Brd_CanBusNo(handle) == kBrd_CanId2' in can
 assert 'Brd_CanBusNo(handle) == kBrd_CanId0' not in can
 for rail in ['kBrd_PwrCtrlBaseId3v3Per','kBrd_PwrCtrlBaseId5vPer']:assert 'Brd_PwrCtrlSetBaseOn('+rail+', enable)' in can
 rtc=files['ac78428/cfg/brd_ext_rtc_cfg.c'];assert 'g_brd_ext_rtc_rx8010sj_' in rtc and 'kRx8010sjChipAddr' in rtc and 'TPerRtcRx8010sjTimerConfig' not in rtc
 card=files['ac78428/cfg/brd_ic_card_cfg.c'];assert '.dev_addr = kPerFramAt24DevAddr' in card or re.search(r'\.dev_addr\s*=\s*kPerFramAt24DevAddr',card)
 assert 'g_brd_ic_card_0_' not in card
 for item in config['board']['modules']['ext_int']:
  text=files['ac78428/cfg/brd_ext_int_cfg.c'];assert item['enum']+', '+item['params']['pin'] in text or item['enum']+' / '+item['name']+', '+item['params']['pin'] in text
 assert '软件工程院' in files['ac78428/def/brd_def.h']
 old=parse(ctx['board_source_root']/'r01v02/ac78428/cfg/brd_flash_cfg.c');new=parse(board/'ac78428/cfg/brd_flash_cfg.c')
 olditems={i['id']:i for i in old['g_brd_flash_items_']};newitems={i['id']:i for i in new['g_brd_flash_items_']};assert olditems.keys()==newitems.keys()
 for enum,before in olditems.items():
  after=newitems[enum]
  for key in ['dev','bus','info','default_offset']:assert numeric(before[key])==numeric(after[key]),(enum,key,before[key],after[key])
  a=deref(old,before['dev_cfg']);b=deref(new,after['dev_cfg']);assert a.get('flag',0)==b.get('flag',0)==0
  assert a['base']['mutex']==b['base']['mutex'] and a['base']['mutex_cnt']==b['base']['mutex_cnt']
  if before['bus_cfg']!='NULL':
   aa=deref(old,before['bus_cfg']);bb=deref(new,after['bus_cfg']);assert aa.get('flag',0)==bb.get('flag',0)==0
   for key in ['bus_drv_parent','bus_drv_parent_cfg']:assert aa['base'].get(key)==bb['base'].get(key)
   if aa['base'].get('bus_drv_cfg'):assert numeric(deref(old,aa['base']['bus_drv_cfg']))==numeric(deref(new,bb['base']['bus_drv_cfg']))
 assert numeric(old['g_per_fee_cfg'])==numeric(new['g_per_fee_cfg'])
 flash=files['ac78428/cfg/brd_flash_cfg.c'];assert 'g_brd_flash_event_[2]' in flash and 'BRD_FLASH_FEE_EEP_RAM_BASE_ADDR' in flash and 'at(536993792)' not in flash
 compile_can(board)
 mixed=copy.deepcopy(config);mixed['board']['modules']['can'][1]['params'].update(fd_enabled=True,fd_enum='kBrd_CanfdId1')
 fd=Path(temp)/'with-fd';generate_project(ctx,mixed,fd);assert (fd/'ac78428/def/brd_canfd_def.h').is_file();compile_can(fd)
 rtcitems=copy.deepcopy(config['board']['modules']['ext_rtc']);rtcitems[0]['params']['timer_custom']=True;assert 'TPerRtcRx8010sjTimerConfig' in ext_rtc(rtcitems,platform,{'iic1':1})
 altered=copy.deepcopy(config['board']['modules']['ic_card']);altered[0]['params']['address']='0xA2';assert '#define BRD_IC_CARD_AT24_ADDRESS 0xA2U' in ic_card(altered,platform)
print('PASS counts; CAN power and no/mixed FD; RTC default/custom; address macros; comments; author; Flash geometry/locks/buses/Fee parameters; ARMCC CAN compilation')
