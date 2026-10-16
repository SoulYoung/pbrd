"""Regression coverage for reviewed multi-product modules and target boundaries."""
from pathlib import Path
import copy,json,sys,tempfile,shutil,subprocess,hashlib
TOOL=Path(__file__).resolve().parents[1];sys.path.insert(0,str(TOOL));sys.path.insert(0,str(TOOL/'ui'))
from generator.engine import generate_project
from generator.c_parser import declarations
from project_context import project_context
from preprocess_cfg import preprocess
context=project_context();root=context['project_root'];config=json.loads((TOOL/'examples/HQT401_L30_R01V02.json').read_text(encoding='utf-8'))
reference_hashes={str(f.relative_to(root)):hashlib.sha256(f.read_bytes()).hexdigest() for name in ('r01v01','r02v01','r03v01','r04v01') for f in (root/'product/src/brd'/name).rglob('*') if f.is_file() and '.git' not in f.parts}
board=context['board_source_root']/'r01v02'
for project in board.glob('build/*/brd.uvprojx'):
    assert project.read_bytes().startswith(b'<?xml version="1.0" encoding="UTF-8" standalone="no" ?>')
for source in board.rglob('*.h'):
    assert '#include "'+source.name+'"' not in source.read_text(encoding='utf-8'),source
app=(board/'ac78428/def/brd_inc.h').read_text(encoding='utf-8')
assert 'brd_debugger.h' not in app and 'brd_security_boot.h' not in app and 'brd_xcu_spi.h' not in app
boot=(board/'ac78428_boot/src/brd_inc.h').read_text(encoding='utf-8')
assert all(name in boot for name in ['brd_debugger.h','brd_security_boot.h','brd_xcu_spi.h'])
partition=(board/'ac78428/def/brd_partition_def.h').read_text(encoding='utf-8')
assert '#define BRD_PARTITION_ID_BOOT_INFO\n' in partition and 'ID_K_BRD' not in partition
can=(board/'ac78428/cfg/brd_can_cfg.c').read_text(encoding='utf-8')
records={d['name']:d['value'] for d in declarations(can)}
assert list(records['g_drv_can_cfgs_'][0])==['rx_group','tx_group','stb_group','rx_pin','tx_pin','stb_pin','tx_pin_mux','rx_pin_mux','id','index']
assert 'RXD PE4, TXD PE5, STB PA30' in can
assert can.count('RXD PE4, TXD PE5, STB PA30')==1
assert '/// 唤醒蓝牙' not in can
assert not any((board/name).exists() for name in ['project-config.json','comparison.patch','COMPARISON.md','generation-report.json','.pbrd-manifest.json','README.md'])
check=(board/'ac78428/check_list.md').read_text(encoding='utf-8')
assert (board/'ac78428_boot/check_list.md').is_file()
assert '| can | 第一路CAN | kBrd_CanId0 | PE4 / PE5 / PA30 |' in check
assert '√' not in check and '| analog | 外部输入电压1 | kBrd_AnalogIdExt0 | PC17 |' in check
axis=(board/'ac78428/cfg/brd_axis_cfg.c').read_text(encoding='utf-8')
assert all(name in axis for name in ['g_brd_axis_per_da280b_','g_brd_axis_dev_da280b_','g_brd_axis_per_lsm6dsl_','g_brd_axis_dev_lsm6dsl_'])
assert 'g_brd_axis_0_per' not in axis and '// #define BRD_AXIS_DEV_MMA8452' in axis
assert axis.count('/// -------使用到的设备配置-------')==1
misc=(board/'ac78428/cfg/brd_misc_ctrl_cfg.c').read_text(encoding='utf-8')
assert misc.count('唤醒蓝牙')==1
print('PASS XML declaration, target headers, self-include, partition macros, CAN order/comments and board deliverables',flush=True)

candidate=copy.deepcopy(config);candidate['targets']={'app':candidate['targets']['app']};candidate['output'].update(mode='create',compare_to='')
def add(module,n,params):
    candidate['board']['modules'].setdefault(module,[]).append({'uid':module+'_'+str(n),'name':'验证'+module+str(n),'enum':'kBrd_'+{'meter':'Meter','ic_card':'IcCard','bat_chg_mgr':'BatChgMgr','ext_rtc':'ExtRtc'}[module]+'IdTest'+str(n),'base_enum':'','targets':['app'],'params':params})
for module in ['meter','ic_card','bat_chg_mgr']:
    candidate['targets']['app']['requested'].append('brd.'+module);candidate['board']['modules'][module]=[]
for n,(pin,instance,channel) in enumerate([('PE8',0,6),('PE13',4,5)]):add('meter',n,dict(pin=pin,instance=instance,channel=channel,wide=False,power_supply='kBrd_PwrCtrlBaseId3v3Per'))
for n,group in enumerate(['A','B']):add('ic_card',n,dict(support_at24=True,support_sle4428=False,support_sle4442=(n==1),power_pin='P'+group+'1',reset_pin='P'+group+'2',detect_pin='P'+group+'3',clock_pin='P'+group+'4',io_pin='P'+group+'5',power_reverse=False,reset_reverse=False,detect_reverse=True,address='',power_supply='kBrd_PwrCtrlBaseId3v3Per'))
for n in range(2):add('bat_chg_mgr',n,dict(enable_pin='PD'+str(14+n*2),done_pin='PD'+str(13+n*2),charging_pin='',enable_reverse=False,done_reverse=False,charging_reverse=False,initial=False))
add('ext_rtc',1,dict(driver='rx8010sj',bus='iic1',address='',timer_clock='kRx8010sjClksrc1Hz',timer_output='kRx8010sjOutPinIrq2'))
out=Path(tempfile.mkdtemp(prefix='pbrd-verification-references-',dir=context['board_source_root']));out.rmdir()
try:
    report=generate_project(context,candidate,out)
    for module,array in [('meter','g_brd_meter_items_'),('ic_card','g_brd_ic_card_item_'),('bat_chg_mgr','g_brd_bat_chg_mgr_items_'),('ext_rtc','g_brd_ext_rtc_item_')]:
        records={d['name']:d['value'] for d in declarations(preprocess(out/'ac78428/cfg'/('brd_'+module+'_cfg.c')))}
        assert len(records[array])==2,(module,records[array])
    text=(out/'ac78428/cfg/brd_ic_card_cfg.c').read_text(encoding='utf-8');assert text.count('static Brd_TIcCardDevItem')==3
    assert '_0_sle4428_dev' not in text and '_0_sle4442_dev' not in text and '_0_at24_dev' in text
    assert '_1_at24_dev' in text and '_1_sle4442_dev' in text
    from generator.modules.additional import ic_card_drivers
    assert ic_card_drivers({'driver':'auto'})==['sle4428','sle4442','at24']
    assert ic_card_drivers({'driver':'at24'})==['at24']
    disabled=copy.deepcopy(candidate);disabled['output']['mode']='regenerate'
    disabled['board']['modules']['ic_card'][0]['params'].update(support_at24=False,support_sle4428=False,support_sle4442=False)
    before_card=(out/'ac78428/cfg/brd_ic_card_cfg.c').read_bytes()
    try:generate_project(context,disabled,out)
    except ValueError as error:assert 'at least one' in str(error)
    else:raise AssertionError('Allowed empty card selection')
    assert (out/'ac78428/cfg/brd_ic_card_cfg.c').read_bytes()==before_card
    assert '.irq_pin = kRx8010sjOutPinIrq2' in (out/'ac78428/cfg/brd_ext_rtc_cfg.c').read_text(encoding='utf-8')
    print('PASS two meter inputs, two card slots / three selected card drivers, two charge channels and two RTC variants',flush=True)
    if '--compile' in sys.argv:
        subprocess.run([sys.executable,'-B',str(TOOL/'tests/compile_project.py'),'--uv4','D:/Keil/UV4/UV4.exe','--board',str(out)],cwd=root,check=True)
finally:
    assert out.resolve().parent==context['board_source_root'].resolve() and out.name.startswith('pbrd-verification-references-')
    if out.exists():shutil.rmtree(out)
for file,digest in reference_hashes.items():assert hashlib.sha256((root/file).read_bytes()).hexdigest()==digest,file
print('PASS all four input references unchanged',flush=True)
