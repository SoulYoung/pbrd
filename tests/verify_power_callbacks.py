"""Power callbacks follow referenced supply names and are shared by all consumers."""
from pathlib import Path
import json,re,sys,copy
TOOL=Path(__file__).resolve().parents[1];sys.path[:0]=[str(TOOL),str(TOOL/'ui')]
from generator.modules.devices import pwr_ctrl
p=json.loads((TOOL/'configs/TXJ_BR4_CX20P_R01V01.json').read_text(encoding='utf-8'));items=p['board']['modules']['pwr_ctrl']
source=pwr_ctrl(items,items)
assert not re.search(r'Brd_PwrCtrlPower\d+',source)
for name,rail in [('Brd_PwrCtrlSet3v3PerEnable','kBrd_PwrCtrlBaseId3v3Per'),('Brd_PwrCtrlSet5vPerEnable','kBrd_PwrCtrlBaseId5vPer')]:
 assert source.count('static void '+name+'(Bool enable)')==1
 assert 'Brd_PwrCtrlSetBaseOn('+rail+', enable);' in source
assert source.count('INIT_PWR_CTRL_CFG(Brd_PwrCtrlSet5vPerEnable,')==2
assert source.count('INIT_PWR_CTRL_CFG(Brd_PwrCtrlSet3v3PerEnable,')==1
reordered=list(reversed(copy.deepcopy(items)));other=pwr_ctrl(reordered,reordered)
assert set(re.findall(r'static void (\w+)\(',source))==set(re.findall(r'static void (\w+)\(',other))
print('PASS named callbacks, shared 5V callback, correct 3.3V/5V mapping and order-independent names')
