"""High-level device forms must drive generated instances, values and dependency wiring."""
from pathlib import Path
import copy,json,sys
TOOL=Path(__file__).resolve().parents[1];sys.path[:0]=[str(TOOL),str(TOOL/'ui')]
from generator.modules import devices,builtins
from generator.c_parser import declarations
from generator.modules.headers import header
config=json.loads((TOOL/'examples/HQT401_L30_R01V02.json').read_text(encoding='utf-8-sig'));platform=json.loads((TOOL/'platforms/ac78428.json').read_text(encoding='utf-8-sig'))
def generate(module,items,target='app'):
 x=copy.deepcopy(config);x['board']['modules'][module]=items;return devices.generate(module,items,x,target,platform)
def records(source,name):return next(d['value'] for d in declarations(source) if d['name']==name)
items=copy.deepcopy(config['board']['modules']['bat_chg']);items.append(copy.deepcopy(items[0]));items[-1]['enum']='kBrd_BatChgIdSecond';source=generate('bat_chg',items)
assert len(records(source,'g_brd_bat_chg_cfg_'))==6 and len(records(source,'g_brd_bat_chg_items_'))==2
assert 'Brd_PwrCtrlSetBaseOn(kBrd_PwrCtrlBaseId3v3Per, enable)' in source
print('PASS battery instance counts and status power dependency')
items=copy.deepcopy(config['board']['modules']['pwr_ctrl']);items[-1]['params']['pin']='PE24';source=generate('pwr_ctrl',items);assert 'INIT_PWR_CTRL_CFG(NULL, E, 24' in source
items.append(copy.deepcopy(items[-1]));items[-1].update(enum='kBrd_PwrCtrlIdExtra',base_enum='',uid='extra');source=generate('pwr_ctrl',items);assert records(source,'g_brd_pwr_ctrl_attr')['count']=='sizeof(g_brd_pwr_ctrl_items_) / sizeof(g_brd_pwr_ctrl_items_[0])' and len(records(source,'g_brd_pwr_ctrl_items_'))==9
assert 'kBrd_PwrCtrlIdExtra' in header('pwr_ctrl',[i for i in items if i['params']['power_kind']=='output'],config['project'])
items[0]['params']['upstream_ref']=items[0]['enum']
try:generate('pwr_ctrl',items);raise AssertionError('power cycle accepted')
except ValueError as error:assert '循环' in str(error)
print('PASS editable power pin, dynamic output count, definition and cycle rejection')
items=[i for i in config['board']['modules']['crypto'] if 'boot' in i['targets']];source=generate('crypto',items,'boot');assert len(records(source,'g_brd_crypto_items_'))==1 and 'TPerHsmCiu98b' not in source
items=copy.deepcopy(config['board']['modules']['crypto']);items[0]['params']['reset_pin']='PD2';assert 'kDrvPortPin2' in generate('crypto',items)
print('PASS crypto target scope and editable reset pin')
items=copy.deepcopy(config['board']['modules']['flash']);source=generate('flash',items[:1]);assert len(records(source,'g_brd_flash_items_'))==1 and 'TPerFramAt24' not in source
items[0]['params']['size']=1048576;source=generate('flash',items[:1]);assert records(source,'g_brd_flash_items_')[0]['info']['sectors_per_block']==128
print('PASS flash selection, count and capacity change actual output')
items=copy.deepcopy(config['board']['modules']['can']);items[0]['params']['fd_enabled']=False;values=builtins.values('can',items,platform);assert len(values['g_brd_canfd_items_'])==3 and values['g_brd_can_dev_in_chip_'][0]['fd_buf']=='NULL'
print('PASS CAN FD switch controls generated data and attribute count')

source=generate('flash',config['board']['modules']['flash']);a=records(source,'g_brd_flash_chip_pflash_dev_')['base'];b=records(source,'g_brd_flash_chip_eep_dev_')['base'];assert a['mutex']==b['mutex'] and a['mutex_cnt']==b['mutex_cnt']
source=generate('crypto',config['board']['modules']['crypto']);assert records(source,'g_brd_crypto_ciu98b_dev')['base']['dev_drv']=='&g_per_hsm_ciu98b'
print('PASS shared internal Flash lock and CIU98B callback singleton preserved')
