"""Template generation regressions: independent build, count mapping, preserving user code."""
from pathlib import Path
import copy,json,sys,tempfile,shutil,hashlib,time,xml.etree.ElementTree as ET
from preprocess_cfg import preprocess
from unittest.mock import patch
TOOL=Path(__file__).resolve().parents[1];sys.path.insert(0,str(TOOL));sys.path.insert(0,str(TOOL/'ui'))
from generator import engine,writer
from generator.c_parser import declarations
from generator.user_sections import sections
from generator.modules import compact,builtins
from generator.c_format import initializer
from generator.c_parser import parse
from project_context import project_context
context=project_context();source=context['board_source_root']/'r01v01';config=json.loads((TOOL/'examples/HQT401_L30_R01V02.json').read_text(encoding='utf-8-sig'))
original={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file() and '.git' not in p.parts}
free=[('PB28','ADC0_IN23'),('PB2','ADC0_IN6'),('PB0','ADC0_IN4'),('PD19','ADC1_IN17'),('PB16','ADC1_IN15')]
normal_read=engine.read

def without_baseline(path):
    if source.resolve() in Path(path).resolve().parents:raise AssertionError('Generation attempted to read baseline '+str(path))
    return normal_read(path)

same_chip=copy.deepcopy(config['board']['modules']['axis'][0]);other_chip=copy.deepcopy(same_chip)
other_chip.update(uid='second_da280b',enum='kBrd_AxisIdDa280bSecond');other_chip['params']['bus']='iic0'
axis_code,_=builtins.axis([same_chip,other_chip],{'iic0':0,'iic1':1})
assert 'g_brd_axis_per_da280b_0_' in axis_code and 'g_brd_axis_per_da280b_1_' in axis_code
assert 'g_brd_axis_dev_da280b_0_' in axis_code and 'g_brd_axis_dev_da280b_1_' in axis_code
print('PASS same-chip multiple Axis instances retain chip names and unique symbols')

for total in [1,8,10]:
    candidate=copy.deepcopy(config);candidate['output'].update(mode='create',compare_to='')
    items=candidate['board']['modules']['analog']
    if total==1:items[:]=[i for i in items if i['params']['channel'].startswith('ADC1_')]
    else:
        while len(items)<total:
            pin,channel=free[len(items)-5];item=copy.deepcopy(items[-1]);item.update(uid='test_'+str(len(items)),name='测试通道'+str(len(items)),enum='kBrd_AnalogIdTest'+str(len(items)),base_enum='');item['params'].update(pin=pin,channel=channel);items.append(item)
    out=Path(tempfile.mkdtemp(prefix='pbrd-verification-',dir=context['board_source_root'])).resolve();out.rmdir()
    try:
        with patch.object(engine,'read',without_baseline):report=engine.generate_project(context,candidate,out)
        assert report['baseline_required'] is False and report['inherited_modules']==[]
        records={d['name']:d['value'] for d in declarations(preprocess(out/'ac78428/cfg/brd_analog_cfg.c'))}
        # Compare actual compiler macro expansion with the pre-compaction values.
        # Capture the adapters' full structured records, independently of argument formatting.
        captured={};original_array=compact.array
        def capture(name,value):
            if name in compact.SPECS:captured[name]=copy.deepcopy(value)
            return original_array(name,value)
        with patch.object(compact,'array',capture),patch.object(builtins,'array',capture):
            engine.generate_project(context,{**candidate,'output':{**candidate['output'],'mode':'regenerate'}},out)
        expanded={}
        for cfg in (out/'ac78428/cfg').glob('*.c'):
            if cfg.name in ['brd_analog_cfg.c','brd_misc_ctrl_cfg.c','brd_pwr_ctrl_cfg.c','brd_uart_cfg.c']:
                expanded.update({d['name']:d['value'] for d in declarations(preprocess(cfg))})
        for name,rows in captured.items():
            expected=copy.deepcopy(rows)
            # Previously omitted pins have C static zero initialization.
            for row in expected:
                if name in ['g_brd_pwr_ctrl_cfgs_','g_brd_pwr_ctrl_base_cfgs_']:row.setdefault('pin','kDrvPortPin0')
                if name=='g_drv_uart_cfgs_':row.setdefault('rts_pin','kDrvPortPin0')
            assert expanded[name]==parse(initializer(expected)),(name,expanded[name],expected)
        assert len(records['g_brd_analog_items_'])==total
        if total==1:
            assert records['g_drv_adc_cfgs_'][0]['index']==1
            assert records['g_brd_analog_dev_in_chips_'][0]['dev_drv_parent']=='&g_drv_adcs_[0]'
        for project in out.glob('build/*/brd.uvprojx'):
            xml=ET.parse(project).getroot()
            for node in xml.iter('FilePath'):
                if node.text:assert (project.parent/node.text.replace('\\','/')).is_file(),node.text
            for node in xml.iter('IncludePath'):
                for directory in (node.text or '').split(';'):
                    if directory and '$' not in directory:assert (project.parent/directory.replace('\\','/')).is_dir(),directory
        original_code={p.relative_to(out):p.read_bytes() for p in out.rglob('*') if p.suffix in ['.c','.h','.bat','.uvprojx']}
        candidate['output']['mode']='regenerate'
        engine.generate_project(context,candidate,out)
        assert all((out/p).read_bytes()==data for p,data in original_code.items())
        wrapper=out/'ac78428/src/brd_axis.c';text=wrapper.read_bytes().decode('utf-8');user='\r\n    /* 用户自定义：原样保留缩进 */\r\n';text=text.replace('/***** User code begin *****/\n\n','/***** User code begin *****/'+user);wrapper.write_bytes(text.encode('utf-8'))
        before=sections(text)['code'];report=engine.generate_project(context,candidate,out);assert sections(wrapper.read_bytes().decode('utf-8'))['code']==before
        assert 'ac78428/src/brd_axis.c' in report['preserved_user_files']
        assert 'ac78428/src/brd_axis.c' in json.loads((Path(report['report_directory'])/'generation-report.json').read_text(encoding='utf-8'))['preserved_user_files']
        if total==8:
            snapshot_all={p.relative_to(out):p.read_bytes() for p in out.rglob('*') if p.is_file()}
            changed=copy.deepcopy(candidate);changed['project']['author']='rollback-test'
            actual_replace=writer.replace;calls=[0]
            def fail_once(a,b):
                calls[0]+=1
                if calls[0]==3:raise OSError('injected write failure')
                return actual_replace(a,b)
            try:
                with patch.object(writer,'replace',fail_once):engine.generate_project(context,changed,out)
            except OSError as error:assert 'injected' in str(error)
            else:raise AssertionError('Fault injection did not execute')
            assert all((out/p).read_bytes()==data for p,data in snapshot_all.items())
            print('PASS failed file commit restores every original generated file')
        candidate['targets']['app']['requested'].remove('brd.axis')
        snapshot=wrapper.read_bytes()
        try:engine.generate_project(context,candidate,out)
        except ValueError as error:assert 'user/manual code' in str(error)
        else:raise AssertionError('Removed nonempty user code silently')
        assert wrapper.read_bytes()==snapshot
        candidate['targets']['app']['requested'].append('brd.axis');wrapper.write_bytes(snapshot+b'\n/* outside user region */\n')
        try:engine.generate_project(context,candidate,out)
        except ValueError as error:assert 'outside user region' in str(error)
        else:raise AssertionError('Overwrote a manual generated-region edit')
        print('PASS',total,'ADC: no baseline read, correct object indices, valid projects, deterministic source, user-area roundtrip and conflict handling')
    finally:
        assert out.parent==context['board_source_root'].resolve() and out.name.startswith('pbrd-verification-')
        for attempt in range(20):
            try:
                if out.exists():shutil.rmtree(out)
                break
            except PermissionError:
                if attempt==19:raise
                time.sleep(0.25)
for file,digest in original.items():assert hashlib.sha256(file.read_bytes()).hexdigest()==digest,file
print('PASS r01v01 remained unchanged')
