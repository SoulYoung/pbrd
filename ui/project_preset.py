"""Read a current BSP into the editor project JSON, with explicit inheritance."""
from pathlib import Path
import re,json,datetime,xml.etree.ElementTree as ET
from catalog_sources import read_enums
from module_library import load_modules
from generator.c_parser import declarations,end_brace,mask
from generator.documentation import source_comments
from generator.modules.builtins import SUPPORTED

def array_records(text,name):
    masked=re.sub(r'/\*.*?\*/|//[^\n]*',lambda m:' '*len(m.group()),text,flags=re.S)
    match=re.search(r'\b'+re.escape(name)+r'\s*\[[^\]]*\]\s*=\s*\{',masked)
    if not match:return []
    start=match.end()-1;depth=0;records=[];record=None
    for index in range(start,len(masked)):
        ch=masked[index]
        if ch=='{':
            depth+=1
            if depth==2:record=index
        elif ch=='}':
            if depth==2 and record is not None:records.append(text[record:index+1])
            depth-=1
            if depth==0:break
    return records

def fields(record):return {m.group(1):m.group(2).strip() for m in re.finditer(r'\.(\w+)\s*=\s*([^,\n{}]+)',re.sub(r'//[^\n]*','',record))}
def number(value):return int(re.sub(r'[uUlL]+$','',str(value)),0)
def pin(group,bit):
    g=re.search(r'kDrvPortGroup([A-Z])$',group or '')
    n=re.search(r'kDrvPortPin(\d+)$',bit or '')
    return 'P'+g.group(1)+n.group(1) if g and n else ''

def project_preset(context,version='r01v01'):
    root=context['project_root'];tool=context['tool_root'];source=context['board_source_root']/version
    if not source.is_dir():raise ValueError('Reference BSP not found: '+str(source))
    specs=load_modules(tool);known={s['id'] for s in specs};catalog=read_enums(context['enum_header'])['enum_catalog'];by_enum={e['enum']:e for e in catalog}
    p={'format':'pbrd-project','schema_version':1,'project':{'model':'HQT401_L30','revision':version.upper(),'hardware_revision':re.match(r'r\d+',version,re.I).group().upper(),'software_revision':re.search(r'v\d+',version,re.I).group().upper(),'author':'软件工程院','date':datetime.date.today().isoformat()},'platform':{'mcu':'ac78428','package':'144LQFP'},'build':{'adapter':'keil','version':'5.23'},'targets':{},'board':{'modules':{s['id']:[] for s in specs},'buses':[]},'driver_settings':{},'baseline':{'source_version':version,'inherit_unmodified_modules':True,'generated_modules':['analog','axis'],'description':'Unmodified modules and build-script frameworks explicitly inherited from the current completed project.'}}
    for target,folder in [('app','ac78428'),('boot','ac78428_boot')]:
        project=source/'build'/folder/'brd.uvprojx'
        if not project.is_file():continue
        x=ET.parse(project).getroot();requested=[]
        for node in x.iter('FilePath'):
            if not node.text:continue
            file=(project.parent/node.text.replace('\\','/')).resolve();m=re.fullmatch(r'brd_(\w+)\.c',file.name)
            if m and m.group(1) in known:requested.append('brd.'+m.group(1))
            m=re.fullmatch(r'drv_(\w+)\.c',file.name)
            if m:requested.append('drv.'+m.group(1))
        p['targets'][target]={'requested':sorted(set(requested)),'disabled':[],'touched':[]}
        common=source/folder/'cfg'/('brd_common_cfg.c' if target=='app' else 'brd_common_cfg_boot.c')
        text=common.read_text(encoding='utf-8-sig')
        for kind,array in [('iic','g_drv_iic_cfgs'),('spi','g_drv_spi_cfgs')]:
            for slot,record in enumerate(array_records(text,array)):
                a=fields(record);instance=number(a['index']);id=kind+str(instance)
                existing=next((b for b in p['board']['buses'] if b['id']==id),None)
                if existing:existing['targets'].append(target);continue
                roles={'SDA':('sda_group','sda_pin','sda_pin_mux'),'SCL':('scl_group','scl_pin','scl_pin_mux')} if kind=='iic' else {'SCK':('clk_group','clk_pin','clk_mux'),'SIN':('sin_group','sin_pin','sin_mux'),'SOUT':('sout_group','sout_pin','sout_mux')}
                p['board']['buses'].append({'id':id,'kind':kind,'instance':instance,'frequency_hz':100000 if kind=='iic' else 1000000,'pins':{role:pin(a[g],a[n]) for role,(g,n,m) in roles.items()},'mux':{role:a[m].replace('kDrvPortMuxAlt','ALT') for role,(g,n,m) in roles.items()},'targets':[target]})
    cfg=(source/'ac78428/cfg/brd_analog_cfg.c').read_text(encoding='utf-8-sig')
    channels=[fields(r) for r in array_records(cfg,'g_drv_adc_ch_cfgs_')]
    parents=[number(fields(r)['index']) for r in array_records(cfg,'g_drv_adc_cfgs_')]
    devices=array_records(cfg,'g_brd_analog_dev_in_chips_');items=[fields(r) for r in array_records(cfg,'g_brd_analog_items_')]
    for i,(a,it,dev) in enumerate(zip(channels,items,devices)):
        parent=int(re.search(r'\.dev_drv_parent\s*=\s*&g_drv_adcs_\[(\d+)\]',dev).group(1))
        enum=it['id'];entry=by_enum.get(enum,{})
        p['board']['modules']['analog'].append({'uid':'analog_'+str(i),'name':entry.get('name',enum),'enum':enum,'base_enum':entry.get('base_enum',''),'enum_override':False,'params':{'pin':pin(a['group'],a['pin']),'channel':'ADC'+str(parents[parent])+'_IN'+str(number(a['index'])),'x':number(a['x']),'y':number(a['y']),'offset':number(a['offset']),'reference_mv':number(a['ref_vol']),'sample_time':a['spt'],'net':''}})
    # Source import is an optional frontend operation. The generator uses only
    # the exported parameters and maintained templates, never this source path.
    layout=json.loads((tool/'platforms/ac78428-generation.json').read_text(encoding='utf-8-sig'))
    p.pop('baseline',None)
    p['codegen']={'adapter':'ac78428-template-v1','parameters':{}}
    by_base={e['base_enum']:e for e in catalog}
    p['project'].update(product_enum='kBrd_VersionHqt401_l30',software_minor=int(p['project']['software_revision'][1:])-1)
    p['output']={'directory':'','automatic':True,'mode':'create','compare_to':version}
    for rel,description in layout['files'].items():
        data={}
        if description['declarations']:
            native=(source/rel).read_text(encoding='utf-8-sig')
            data['values']={d['name']:d['value'] for d in declarations(native)}
            data['comments']=source_comments(native)
        if description['definition']:
            definition=description['definition'];header=(source/rel).read_text(encoding='utf-8-sig');entries=[]
            for old in definition['entries']:
                entry=dict(old);match=re.search(r'^\s*'+re.escape(entry['enum'])+r'\s*=\s*(.*?),\s*(?:///<?\s*([^\n]+))?',header,re.M)
                if match:
                    expression=match[1];base=re.search(r'BRD_DEF_BASE_ID\(\s*(\w+)',expression)
                    entry['base_enum']=base[1] if base else '';entry['value']=expression
                    if match[2]:entry['name']=match[2].strip()
                if entry.get('base_enum') in by_base:entry['name']=by_base[entry['base_enum']]['name']
                entries.append(entry)
            data['definitions']=entries
        if data:p['codegen']['parameters'][rel]=data
    def bind(value,target):
        if isinstance(value,str):
            match=re.fullmatch(r'&g_drv_(iic|spi)(_cfgs)?\[(\d+)\]',value)
            if match:
                buses=[b for b in p['board']['buses'] if b['kind']==match[1] and target in b['targets']]
                return {'$resource':{'kind':match[1],'id':buses[int(match[3])]['id'],'configuration':bool(match[2])}}
        if isinstance(value,dict):return {k:bind(v,target) for k,v in value.items()}
        if isinstance(value,list):return [bind(v,target) for v in value]
        return value
    for rel,parameter in p['codegen']['parameters'].items():
        if 'values' in parameter:parameter['values']=bind(parameter['values'],'boot' if rel.startswith('ac78428_boot/') else 'app')
    for parameter in p['codegen']['parameters'].values():
        for definition in parameter.get('definitions',[]):by_enum[definition['enum']]=definition
    def make(module,n,enum,values):
        entry=by_enum.get(enum,{})
        defaults={f['key']:f['value'] for s in specs if s['id']==module for f in s['fields']}
        return {'uid':module+'_'+str(n),'name':entry.get('name',enum),'enum':enum,'base_enum':entry.get('base_enum',''),'enum_override':False,'label_source':'catalog','params':{**defaults,**values}}
    def values(module):return p['codegen']['parameters']['ac78428/cfg/brd_'+module+'_cfg.c']['values']
    for module,cfg,records in [('led','g_brd_led_cfg_','g_brd_led_items_'),('ext_int','g_brd_ext_int_cfgs','g_brd_ext_int_items_'),('misc_ctrl','g_brd_misc_ctrl_cfgs_','g_brd_misc_ctrl_items_')]:
        a=values(module);rows=[]
        for n,(record,item) in enumerate(zip(a[cfg],a[records])):
            v={'pin':pin(record.get('group',record.get('port')),record['pin'])}
            if module=='ext_int':
                mapping={'Disabled':'disabled','Rising':'rising','Falling':'falling','EdgeBoth':'both'}
                v.update(run_trigger=mapping[record['run_trigger'].replace('kDrvGpioIntTrigger','')],sleep_trigger=mapping[record['sleep_trigger'].replace('kDrvGpioIntTrigger','')],pull='disabled')
            else:v.update(reverse=record['reverse'],initial=item.get('is_on',item.get('enabled',False)),flag=number(record.get('flag',0)))
            rows.append(make(module,n,item['id'],v))
        p['board']['modules'][module]=rows
    for module in ['can','uart']:
        a=values(module);records=a['g_brd_'+module+'_items_'];rows=[]
        for n,item in enumerate(records):
            dev_index=int(re.search(r'\[(\d+)\]',item['dev_cfg'])[1])
            device=a['g_brd_'+module+'_dev_in_chip_'][dev_index]
            cfg_index=int(re.search(r'\[(\d+)\]',device['base']['dev_drv_cfg'])[1])
            record=a['g_drv_'+module+'_cfgs_'][cfg_index]
            hardware=number(record['index']);v={'instance':module.upper()+str(hardware),'rx':pin(record['rx_group'],record['rx_pin']),'tx':pin(record['tx_group'],record['tx_pin'])}
            role='stb' if module=='can' else 'rts';v[role]=pin(record.get(role+'_group'),record.get(role+'_pin'))
            if module=='uart':v.update(mode=record['mode'].replace('kDrvUartMode',''),dma=record['dma_en'],dma_rx=number(record['dma_ch_rx']),dma_tx=number(record['dma_ch_tx']))
            else:v.update(fd_enum=a['g_brd_canfd_items_'][n]['id'])
            rows.append(make(module,n,item['id'],v))
        p['board']['modules'][module]=rows
    rtc=values('ext_rtc')
    for n,item in enumerate(rtc['g_brd_ext_rtc_item_']):
        driver='rx8010sj' if 'Rx8010sj' in item['dev'] else 'bm8563'
        device=rtc[re.search(r'&(\w+)',item['dev_cfg'])[1]]
        bus=rtc[re.search(r'&(\w+)',item['bus_cfg'])[1]]['base']['bus_drv_parent']['$resource']['id']
        enumeration='kBrd_ExtRtcId'+('Bm8563' if driver=='bm8563' else 'Rx8010sj')
        entry=make('ext_rtc',n,enumeration,{'driver':driver,'bus':bus,'address':''})
        if entry['name']==enumeration:entry['name']=driver.upper()
        p['board']['modules']['ext_rtc'].append(entry)
    a=values('switch');rows=[]
    for n,(record,item) in enumerate(zip(a['g_brd_switch_cfgs_'],a['g_brd_switch_items_'])):
        match=re.fullmatch(r'INIT_SWITCH_DEV_IN_CHIP_CFG\(([^,]+),\s*(\d+),\s*(\w+),\s*(\w+)\)',record)
        enumeration=re.search(r'(kBrd_SwitchId\w+)',item)[1]
        rows.append(make('switch',n,enumeration,{'pin':'P'+match[1]+match[2],'pull':match[3].lower(),'reverse':match[4]=='True'}))
    p['board']['modules']['switch']=rows
    if 'boot' in p['targets'] and 'brd.xcu_spi' in p['targets']['boot']['requested']:
        defaults={f['key']:f['value'] for spec in specs if spec['id']=='xcu_spi' for f in spec['fields']}
        defaults.update(clk='PB14',sout='PB16',sin='PB15',cs='PB17',req='PA17')
        reference='product/src/brd/r04v01/ac78428_boot/cfg/brd_xcu_spi_cfg_boot.c'
        p['board']['modules']['xcu_spi']=[{'uid':'xcu_spi_0','name':'XCU Boot SPI','enum':'kBrd_XcuSpiId0','base_enum':'','enum_override':False,'targets':['boot'],'params':defaults,'reference_source':reference}]
        p['metadata']={'import_warnings':['r01v01 Boot 工程引用 XCU SPI 但缺 cfg；XCU SPI 参数暂取 r04v01 参考，需核对项目引脚和极性。']}
    can_source=source/'ac78428/cfg/brd_can_cfg.c'
    if can_source.is_file():
        native=can_source.read_text(encoding='utf-8-sig')
        guard=re.search(r'if\s*\(\s*(kBrd_CanId\w+)\s*!=\s*Brd_CanBusNo\(handle\)\s*\)\s*\{([^}]+)\}',native)
        if guard:
            references=list(dict.fromkeys(re.findall(r'Brd_PwrCtrlSetBaseOn\(\s*(\w+),\s*True\s*\)',guard[2])))
            if len(references)>2:raise ValueError('CAN source needs more than two public supplies; import adapter requires extension')
            for item in p['board']['modules']['can']:
                selected=references if item['enum']!=guard[1] else []
                item['params'].update(power_ref=selected[0] if selected else '',power_ref_aux=selected[1] if len(selected)>1 else '')
    callbacks={}
    for cfg in source.rglob('*cfg*.c'):
        text=cfg.read_text(encoding='utf-8-sig')
        for name,enum in re.findall(r'(?:static\s+)?void\s+(\w+)\s*\(Bool\s+enable\)\s*\{\s*Brd_PwrCtrlSetBaseOn\((\w+),\s*enable\);\s*\}',text):
            if name in callbacks and callbacks[name]!=enum:raise ValueError('Ambiguous power callback: '+name)
            callbacks[name]=enum
    p.setdefault('metadata',{})['import_callback_references']=callbacks
    p['codegen']['lifecycle']={}
    for target,folder in [('app','ac78428'),('boot','ac78428_boot')]:
        common=source/folder/'cfg'/('brd_common_cfg.c' if target=='app' else 'brd_common_cfg_boot.c')
        if target not in p['targets'] or not common.is_file():continue
        text=common.read_text(encoding='utf-8-sig');clean=mask(text);functions={}
        values={d['name']:d['value'] for d in declarations(text)}
        if 'g_brd_version_' in values:p['targets'][target]['software_minor']=values['g_brd_version_']['ver'][3]
        for name in ['Brd_DiffInit','Brd_DiffDone','Brd_DiffOpen','Brd_DiffClose']:
            match=re.search(r'void\s+'+name+r'\s*\(void\)\s*\{',clean)
            if match:functions[name]=text[match.end():end_brace(clean,match.end()-1)-1].strip('\n\r')
        p['codegen']['lifecycle'][target]=functions
    return p
