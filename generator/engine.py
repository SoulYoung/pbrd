"""Single JSON → templates → project orchestration; no runtime baseline inheritance."""
from pathlib import Path
import copy,json,re,hashlib,difflib,datetime
from generator.template import TOKEN,render_file
from generator.c_format import initializer,identifier,scalar,macro
from generator.c_parser import declarations
from generator.user_sections import add
from generator.writer import publish
from generator.modules import builtins,compact,additional,devices
from generator.registry import resolve_modules
from generator.modules.headers import header
from generator.projects.keil import assemble
from generator.capabilities import render as capability_macros
from generator.documentation import annotate,comments,checklist,item_label

def read(path):
    data=Path(path).read_bytes()
    try:return data.decode('utf-8-sig').replace('\r\n','\n').replace('\r','')
    except UnicodeDecodeError:return data.decode('gb18030').replace('\r\n','\n').replace('\r','')

def module_name(rel):
    name=Path(rel).stem
    if name in ['brd_def','brd_inc','brd_inc_all']:return None
    name=re.sub(r'^brd_','',name);name=re.sub(r'_(?:cfg|def)(?:_boot)?$','',name)
    return 'can' if name=='canfd' else name

def count(name,values,fallback):
    serialized=json.dumps(values);references=[int(n) for n in re.findall(r'\b'+re.escape(name)+r'\[(\d+)\]',serialized)]
    return max(references)+1 if references else fallback

def bus_values(values,buses,platform,target):
    # Resource positions and their hardware instances are distinct.
    names=[d['name'] for d in declarations(values)] if isinstance(values,str) else []
    slots={};rows={}
    for kind in ['iic','spi']:
        selected=[b for b in buses if b['kind']==kind and target in b.get('targets',['app','boot'])];result=[]
        if kind=='iic':slots={b['id']:n for n,b in enumerate(selected)}
        for b in selected:
            row={};roles={'SCL':('scl','_pin_mux'),'SDA':('sda','_pin_mux')} if kind=='iic' else {'SCK':('clk','_mux'),'SIN':('sin','_mux'),'SOUT':('sout','_mux')}
            for role,(prefix,suffix) in roles.items():
                group,pin=builtins.port(b['pins'][role]);row[prefix+'_group']=group;row[prefix+'_pin']=pin;row[prefix+suffix]=builtins.pinmux(platform,b['pins'][role],('I2C' if kind=='iic' else 'SPI')+str(b['instance'])+'_'+role)
            row['index']=b['instance']
            if kind=='spi':row['reverse']=b.get('reverse',False)
            result.append(row)
        rows['g_drv_'+kind+'_cfgs']=result
    return rows,slots

def lifecycle(source,effective):
    result=[]
    for line in source.splitlines():
        call=re.search(r'\bBrd_([A-Z][a-z]+(?:[A-Z][a-z]+)*?)(Init|Done|Open|Close)',line)
        if call:
            module=re.sub(r'(?<=[a-z])(?=[A-Z])','_',call[1]).lower()
            if 'brd.'+module not in effective:continue
        result.append(line)
    return '\n'.join(result).strip('\n')

def generate_project(context,config,output=None):
    from module_library import load_modules
    config=copy.deepcopy(config);root=context['project_root'];tool=context['tool_root'];project=config['project']
    if config.get('format')!='pbrd-project' or config.get('schema_version')!=1:raise ValueError('Expected pbrd-project schema_version=1')
    if config['platform']['mcu']!='ac78428' or config['build']!={'adapter':'keil','version':'5.23'}:raise ValueError('Implemented project adapter: AC78428 / Keil 5.23')
    combined=re.fullmatch(r'(r\d+)(v\d+)',project.get('revision',''),re.I)
    hardware=project.get('hardware_revision',combined[1] if combined else '');software=project.get('software_revision',combined[2] if combined else '')
    if not re.fullmatch(r'R\d+',hardware,re.I) or not re.fullmatch(r'V\d+',software,re.I):raise ValueError('Expected Rxx hardware and Vxx software versions')
    version=(hardware+software).lower();project.update(hardware_revision=hardware,software_revision=software,revision=hardware+software)
    if not project.get('model','').strip() or not project.get('date'):raise ValueError('Project model/date required')
    product=identifier(project.get('product_enum',''));minor=int(project.get('software_minor',int(software[1:])-1))
    if not 0<=minor<=255:raise ValueError('Software minor must be 0..255')
    for key in ['model','author','date']:
        if any(token in str(project.get(key,'')) for token in ['\n','\r','*/']):raise ValueError('Invalid project metadata: '+key)
    epoch=int(config.get('metadata',{}).get('build_time',datetime.datetime.fromisoformat(project['date']).replace(tzinfo=datetime.timezone(datetime.timedelta(hours=8))).timestamp()))
    settings=config.get('output',{});selected=output or (settings.get('directory') if settings.get('automatic') is False else None)
    if settings.get('automatic') is False and not selected:raise ValueError('Output directory required')
    output=Path(selected) if selected else context['board_source_root']/version
    output=(output if output.is_absolute() else root/output).resolve()
    if output.parent!=context['board_source_root'].resolve() or not re.fullmatch(r'r\d+v\d+|pbrd-verification-[\w-]+',output.name,re.I):raise ValueError('Output must be a board version directory directly under product/src/brd')
    if output.name.lower()=='r01v01':raise ValueError('This implementation trial must not overwrite the original r01v01')
    specs={m['id']:m for m in load_modules(tool)};layout=json.loads(read(tool/'platforms/ac78428-generation.json'));platform=json.loads(read(tool/'platforms/ac78428.json'))
    if config.get('ui_schema_version',1)>=2 and not config.get('codegen'):
        defaults=json.loads(read(tool/'platforms/ac78428-defaults.json'));config['codegen']={'adapter':defaults['adapter'],'parameters':defaults['parameters']}
    codegen=config.get('codegen',{})
    if codegen.get('adapter')!='ac78428-template-v1':raise ValueError('JSON needs complete template parameters; import current project again or use the new template example')
    if config.get('driver_settings'):raise ValueError('Extra driver_settings have no adapter yet; configure the module/resources instead')
    parameters=codegen['parameters'];targets=config['targets']
    dynamic={k for k in devices.SUPPORTED if config['board']['modules'].get(k)}
    if not targets or set(targets)-{'app','boot'}:raise ValueError('Targets must be app/boot')
    effective={t:resolve_modules(config,specs,t,layout.get('native_dependencies',{}).get(t,{})) for t in targets}
    for target,modules in effective.items():
        available={m['module'] for m in layout['targets'][target]['members'] if m['module']}|{'brd.axis'}
        available.update('brd.'+k for k,v in layout.get('extensions',{}).items() if target in v['targets'])
        unsupported=sorted(id for id in modules if id.startswith(('brd.','drv.')) and id not in available)
        for id in modules:
            if id.startswith('brd.') and specs.get(id[4:],{}).get('configuration_status')=='reference-only':raise ValueError(id+': reference exists but configuration/project adapter is incomplete')
        if unsupported:raise ValueError(target+': no reviewed template/project adapter for '+', '.join(unsupported))
        if any(id.startswith('hal.') for id in modules):raise ValueError(target+': HAL generation adapter not implemented')
        if not {'drv.common','drv.clock','drv.gpio','drv.irq','drv.port'}.issubset(modules):raise ValueError(target+': required foundational drivers disabled')
    if config.get('ui_schema_version',1)>=2:
        for target,enabled in effective.items():
            for module in builtins.SUPPORTED|additional.SUPPORTED|devices.SUPPORTED:
                if 'brd.'+module not in enabled:continue
                items=[i for i in config['board']['modules'].get(module,[]) if target in i.get('targets',list(targets))]
                if not items:raise ValueError(target+'/'+module+'：已使能，请先在网页中添加并配置实例')
                for item in items:
                    if item.get('review_note'):raise ValueError(item['name']+'：旧配置需要核对；请在网页确认后再生成')
    for module,items in config['board']['modules'].items():
        if module not in builtins.SUPPORTED|additional.SUPPORTED|devices.SUPPORTED and items and any('brd.'+module in enabled for enabled in effective.values()):raise ValueError(module+': use template parameter editor until its high-level adapter is implemented')
        enums=set()
        for item in items:
            identifier(item['enum'])
            if item['enum'] in enums:raise ValueError('Duplicate enum: '+item['enum'])
            if '\n' in item['name'] or '\r' in item['name'] or '*/' in item['name']:raise ValueError('Invalid item name')
            if item.get('base_enum'):identifier(item['base_enum'])
            enums.add(item['enum'])
        if len(items)>64:raise ValueError(module+': handle map capacity is 64')
    def occupied(value):
        result=set()
        if isinstance(value,dict):
            for key,group in value.items():
                if isinstance(group,str) and re.fullmatch(r'kDrvPortGroup[A-Z]',group) and (key.endswith('group') or key=='port'):
                    pin=value.get(key[:-5]+'pin' if key.endswith('group') else 'pin')
                    if isinstance(pin,str) and re.fullmatch(r'kDrvPortPin\d+',pin):result.add('P'+group[-1]+pin[len('kDrvPortPin'):])
                result.update(occupied(group))
        elif isinstance(value,list):
            for entry in value:result.update(occupied(entry))
        elif isinstance(value,str):
            match=re.search(r'INIT_SWITCH_DEV_IN_CHIP_CFG\(([A-Z]),\s*(\d+)',value)
            if match:result.add('P'+match[1]+match[2])
        return result
    for target,enabled in effective.items():
        used=set()
        for rel,data in parameters.items():
            if '/cfg/' not in rel or module_name(rel) in builtins.SUPPORTED|dynamic or module_name(rel)=='common' or (rel.startswith('ac78428_boot/') and target!='boot'):continue
            if module_name(rel)=='common' or 'brd.'+str(module_name(rel)) in enabled:used.update(occupied(data.get('values',{})))
        for module,items in config['board']['modules'].items():
            if module=='analog' or 'brd.'+module not in enabled:continue
            for item in items:
                used.update(v for k,v in item['params'].items() if k in ['pin','rx','tx','stb','rts'] and isinstance(v,str) and re.fullmatch(r'P[A-Z]\d+',v))
        for bus in config['board']['buses']:
            if target in bus.get('targets',['app','boot']):used.update(bus['pins'].values())
        seen=set()
        for item in config['board']['modules'].get('analog',[]):
            pin=item['params']['pin']
            if pin in used or pin in seen:raise ValueError(target+': ADC pin conflicts with another board function: '+pin)
            seen.add(pin)
    for module in (builtins.SUPPORTED|{'ext_rtc'}|dynamic)-{'axis','crypto'}:
        subsets=[[i['uid'] for i in config['board']['modules'].get(module,[]) if target in i.get('targets',list(targets))] for target in targets if 'brd.'+module in effective[target]]
        if subsets and any(ids!=subsets[0] for ids in subsets):raise ValueError(module+': this platform shares configuration across App/Boot; differing subsets need a separate target adapter')
    union=set().union(*effective.values());folders={t:d['folder'] for t,d in layout['targets'].items()};buses=config['board']['buses'];bus_rows={};bus_slots={}
    for target in targets:bus_rows[target],bus_slots[target]=bus_values({},buses,platform,target)
    # Native pointer arrays use the JSON resource bindings established by the importer.
    def resources(value,target):
        if isinstance(value,dict) and '$resource' in value:
            resource=value['$resource'];kind=resource['kind'];selected=[b for b in buses if b['kind']==kind and target in b.get('targets',['app','boot'])]
            index=next((n for n,b in enumerate(selected) if b['id']==resource['id']),None)
            if index is None:raise ValueError('Missing resource '+resource['id']+' for '+target)
            return '&g_drv_'+kind+('_cfgs' if resource['configuration'] else '')+'['+str(index)+']'
        if isinstance(value,dict):return {k:resources(v,target) for k,v in value.items()}
        if isinstance(value,list):return [resources(v,target) for v in value]
        return value
    generated={};provenance={};counts={t:{} for t in targets};axis_sources={};definitions={}
    for rel,description in layout['files'].items():
        owner='boot' if rel.startswith('ac78428_boot/') or rel.startswith('build/ac78428_boot/') else 'app' if rel.startswith('ac78428/') or rel.startswith('build/ac78428/') else None
        module=module_name(rel)
        if module in dynamic and ('/cfg/' in rel or '/def/' in rel):continue
        if module in builtins.SUPPORTED and config['board']['modules'].get(module) and ('/def/' in rel or module=='analog' and '/cfg/' in rel):continue
        if module in additional.SUPPORTED and (config['board']['modules'].get(module) or not description['declarations']) and ('/cfg/' in rel or '/def/' in rel):continue
        if Path(rel).suffix.lower()=='.md' or Path(rel).name=='.gitignore':continue
        if owner=='boot' and owner not in targets:continue
        scope=effective.get(owner,union)
        intrinsic=False
        if module and ('/cfg/' in rel or '/def/' in rel or '/src/' in rel) and module not in ['common'] and 'brd.'+module not in (scope if '/src/' in rel else union) and not intrinsic:continue
        if '/src/' in rel and Path(rel).suffix=='.c' and owner not in targets:continue
        if description['declarations']:
            if rel not in parameters and module not in builtins.SUPPORTED:raise ValueError('Missing template parameters: '+rel)
            values=resources(copy.deepcopy(parameters.get(rel,{}).get('values',{})),owner if owner in targets else next(iter(targets)))
            if module in builtins.SUPPORTED and module not in ['analog','axis']:
                items=[i for i in config['board']['modules'][module] if owner in i.get('targets',list(targets)) or owner not in targets]
                if not items:raise ValueError(module+': add at least one instance')
                values.update(builtins.values(module,items,platform));counts.setdefault(owner,{})[module]=len(items)
            if module=='common':
                values.update(bus_rows.get(owner,bus_rows[next(iter(targets))]))
                if 'g_brd_version_' in values:values['g_brd_version_'].update(ver=['kBrd_VersionMajor','(UInt8)'+product,'kBrd_VersionBoot' if owner=='boot' else 'kBrd_VersionApp',minor],build_time=epoch)
            context_values={'DATA_'+d['name'].upper():compact.array(d['name'],values[d['name']]) for d in description['declarations']}
            for entry in description['counts']:
                number=len(values['g_drv_'+('iic' if entry['name']=='g_drv_iic' else 'spi')+'_cfgs']) if entry['name'] in ['g_drv_iic','g_drv_spi'] else count(entry['name'],values,entry['original'])
                context_values['COUNT_'+entry['name'].upper()]=number
            if module=='common':
                for name,source in layout['lifecycle'][owner].items():context_values[name.upper()]=lifecycle(source,scope)
        else:context_values={}
        if description['definition']:
            family=description['definition']['family'];entries=parameters.get(rel,{}).get('definitions')
            if entries is None:raise ValueError('Missing definition parameters: '+rel)
            rows=[(description['definition']['base_name'],'0','基础值')]
            for index,item in enumerate(entries):
                expression='BRD_DEF_BASE_ID('+item['base_enum']+', '+str(index)+')' if item.get('base_enum') else item.get('value') or description['definition']['base_name']+' + '+str(index)
                rows.append((identifier(item['enum']),expression,item['name']))
            width=max(len(r[0]) for r in rows)+4
            context_values['ENUM_CONTENT']='\n'.join('    '+r[0].ljust(width)+'= '+(r[1]+',').ljust(56)+'///< '+r[2] for r in rows)+'\n    '+description['definition']['max_name']+(' = '+description['definition']['max_expression'] if description['definition']['max_expression'] else '')+','
            context_values['DEFINE_CONTENT']='\n'.join('#define '+macro(module,item['enum'],family) for item in entries)
        if module=='can' and description['declarations']:
            fd=values['g_brd_canfd_items_'];context_values['CANFD_BUFFER_DECLARATION']='static TCanfdData g_brd_canfd_data_['+str(len(items))+'];' if fd else ''
            context_values['CANFD_ITEM_DECLARATION']='static Brd_TCanItem g_brd_canfd_items_[] =\n'+initializer(fd)+';' if fd else ''
        source=read(tool/'templates'/description['template']);tokens=set(TOKEN.findall(source))
        if 'EEP_RAM_SIZE' in tokens or 'EEP_RAM_ADDRESS' in tokens:
            fee=values['g_per_fee_cfg']
            def literal(value):
                result=scalar(value);match=re.fullmatch(r'(0x[0-9A-Fa-f]+|\d+)[uUlL]*',result);return match[1] if match else result
            context_values['EEP_RAM_SIZE']=literal(fee['eep_size']);context_values['EEP_RAM_ADDRESS']=literal(fee['eep_ram_base_addr'])
        if 'DATE' in tokens:context_values['DATE']=project['date']
        if 'AUTHOR' in tokens:context_values['AUTHOR']=project.get('author','')
        context_values={k:v for k,v in context_values.items() if k in tokens}
        generated[rel]=render_file(tool/'templates'/description['template'],context_values);provenance[rel]={'template':description['template'],'parameters':rel if rel in parameters else 'fixed platform implementation'}
    # Reusable, reviewed high-level adapters replace generic data with authoritative instances.
    for target in targets:
        folder=folders[target]
        for module in builtins.SUPPORTED|additional.SUPPORTED|dynamic:
            if 'brd.'+module not in effective[target]:continue
            items=[i for i in config['board']['modules'].get(module,[]) if target in i.get('targets',list(targets))]
            if not items:
                if module=='ext_rtc' and config.get('ui_schema_version',1)<2:continue  # Legacy structured parameters only.
                raise ValueError(target+'/'+module+': add at least one instance')
            counts[target][module]=len(items)
            if module in dynamic:
                destination=folder if module=='crypto' else folders['app']
                suffix='_boot' if module=='crypto' and target=='boot' else ''
                rel=destination+'/cfg/brd_'+module+'_cfg'+suffix+'.c'
                generated[rel]=devices.generate(module,items,config,target,platform)
                provenance[rel]={'adapter':'modules/devices.py','source':'board.modules.'+module,'template':'ac78428/power.cfg.c.template' if module=='pwr_ctrl' else 'ac78428/devices.cfg.c.template'}
            elif module=='analog':
                destination=folders['app'] # Existing boot platform shares this module configuration.
                generated[destination+'/cfg/brd_analog_cfg.c']=builtins.analog(items,platform)
            elif module=='axis':
                generated[folder+'/cfg/brd_axis_cfg.c'],axis_sources[target]=builtins.axis(items,bus_slots[target]);destination=folder
                generated[folder+'/src/brd_axis.c']=render_file(tool/'templates/common/brd_module.c.template',{'MODULE':'axis','MCU':'ac78428'})
                inc=folder+'/src/brd_inc_all.h';needed=['#include <per_axis_'+i['params']['driver']+'_ex.h>' for i in items]
                generated[inc]=generated[inc].replace('#include "brd_inc.h"','\n'.join(sorted(set(needed)))+'\n#include "brd_inc.h"')
                if target=='boot':
                    entry=folder+'/src/brd_inc.h';generated[entry]=generated[entry].replace('#include "brd_def.h"','#include "brd_def.h"\n#include "brd_axis_def.h"\n#include "brd_axis.h"')
                if '#include "brd_axis_ac78428.h"' not in generated[inc]:generated[inc]=generated[inc].replace('#include "brd_analog_ac78428.h"','#include "brd_axis_ac78428.h"\n#include "brd_analog_ac78428.h"')
            elif module in additional.SUPPORTED:
                if target not in layout['extensions'][module]['targets']:raise ValueError(module+': no reviewed '+target+' adapter')
                destination=folders['app'] if module=='ext_rtc' else folder
                generated[destination+'/cfg/brd_'+module+'_cfg.c']=additional.generate(module,items,platform,bus_slots[target])
                entry=folder+'/src/brd_inc_all.h'
                for name in layout['extensions'][module]['required_headers']:
                    if re.search(r'^\s*#include\s*[<"]'+re.escape(name)+r'[>"]',generated[entry],re.M):continue
                    anchor='#include "brd_inc.h"' if not name.startswith('brd_') else '/***** User code begin *****/'
                    generated[entry]=generated[entry].replace(anchor,'#include <'+name+'>\n'+anchor,1)
            else:destination=folders['app']
            definitions=[i for i in items if module!='pwr_ctrl' or i['params'].get('power_kind')!='base']
            if module!='bat_chg':generated[destination+'/def/brd_'+module+'_def.h']=header(module,definitions,project)
            if module=='can':
                fd=[{**i,'enum':i['params'].get('fd_enum') or i['enum'].replace('kBrd_CanId','kBrd_CanfdId'),'base_enum':i.get('base_enum','').replace('CanBase','CanfdBase')} for i in items if i['params'].get('fd_enabled',bool(i['params'].get('fd_enum')))]
                generated[destination+'/def/brd_canfd_def.h']=header('canfd',fd,project)
            for rel in [destination+'/def/brd_'+module+'_def.h',destination+'/cfg/brd_'+module+'_cfg.c']:
                if module in dynamic and '/cfg/' in rel:continue
                if rel in generated:provenance[rel]={'adapter':('modules/devices.py' if module in dynamic else 'modules/builtins.py'),'source':'board.modules.'+module,'template': 'common/brd_def.h.template' if '/def/' in rel else 'ac78428/'+module+'.cfg.c.template' if module in ['axis','analog'] else layout['files'][rel]['template']}
    # Remove unselected platform headers as well as exported interfaces: these
    # headers depend on the module types declared by brd_inc.h.
    for target in targets:
        rel=folders[target]+'/src/brd_inc_all.h'
        lines=[]
        for line in generated[rel].splitlines():
            include=re.match(r'^\s*#include\s*[<"](brd_[^">]+)[">]',line)
            if include and ('_mcu' in include[1] or '_ac78428' in include[1]):
                module=next((k for k in sorted(specs,key=len,reverse=True) if include[1].startswith('brd_'+k+'_')),None)
                if module and 'brd.'+module not in effective[target]:continue
            lines.append(line)
        generated[rel]='\n'.join(lines)+'\n'
    # App and Boot export only their own capabilities. Boot may share App's
    # module definition files through include paths, but never its summary header.
    for target in targets:
        folder=folders[target];scope=effective[target]
        for rel in [r for r in generated if r.startswith(folder+'/') and Path(r).name in ['brd_def.h','brd_inc.h']]:
            is_def=Path(rel).name=='brd_def.h'
            modules={id[4:] for id in scope if id.startswith('brd.')}|({'canfd'} if 'brd.can' in scope else set())
            includes=['#include "brd_common_def.h"'] if is_def else ['#include "brd_def.h"']
            if is_def:
                for module in sorted(modules):
                    name='brd_'+module+'_def.h'
                    if any(Path(r).name==name and '/def/' in r for r in generated):includes.append('#include "'+name+'"')
            else:
                includes+=['#include "brd_'+m+'.h"' for m in sorted(modules) if (root/'product/src/brd/base/inc'/('brd_'+m+'.h')).is_file()]
            text=re.sub(r'^#include[^\n]*\n','',generated[rel],flags=re.M)
            text=re.sub(r'(#define _BRD_(?:DEF|INC)_H_[^\n]*\n)(?:[ \t]*\n)*',lambda m:m[1]+'\n'+'\n'.join(includes)+'\n\n',text,count=1)
            generated[rel]=text
    for target in targets:
        rel,content=assemble(context,layout,target,effective[target],generated,axis_sources.get(target,[]),output,version);generated[rel]=content;provenance[rel]={'adapter':'projects/keil.py','template':layout['projects'][target]}
        script='build/'+folders[target]+'/after_build.bat';exports=sorted({id[4:] for id in effective[target] if id.startswith('brd.') and (root/'product/src/brd/base/inc'/('brd_'+id[4:]+'.h')).is_file()}|({'canfd'} if 'brd.can' in effective[target] else set()))
        generated[script]=re.sub(r'^set BRD_INCS=.*$',lambda m:'set BRD_INCS='+','.join(exports),generated[script],count=1,flags=re.M);generated[script]=re.sub(r'^set BRD_INCS=%BRD_INCS%,.*(?:\r?\n)?','',generated[script],flags=re.M)
    for rel in list(generated):
        if '/cfg/' not in rel or not rel.endswith('.c'):continue
        module=module_name(rel);items=config['board']['modules'].get(module,[])
        values=parameters.get(rel,{}).get('values',{})
        if module in builtins.SUPPORTED and module not in ['analog','axis']:values=builtins.values(module,items,platform)
        if module=='analog':
            labels={'g_drv_adc_ch_cfgs_':[item_label(i) for i in items]}
        else:
            defs=parameters.get(rel.replace('/cfg/','/def/').replace('_cfg.c','_def.h'),{}).get('definitions',[])
            labels=comments(module,items,values,defs) if items else parameters.get(rel,{}).get('comments',{})
        generated[rel]=annotate(generated[rel],labels)
        generated[rel]=capability_macros(generated[rel],layout.get('configuration_macros',{}).get(module,[]))
    for target in targets:generated[folders[target]+'/check_list.md']=checklist(config,target,effective[target],parameters)
    # Comparison is diagnostic only; it cannot supply generation data.
    reference=settings.get('compare_to','');baseline=(context['board_source_root']/reference) if reference else None;patch=[];changed=[]
    if reference and (not re.fullmatch(r'r\d+v\d+',reference,re.I) or not baseline.is_dir()):raise ValueError('Invalid comparison reference')
    for rel,value in sorted(generated.items()):
        original=read(baseline/rel) if baseline is not None and (baseline/rel).is_file() else ''
        if original.replace('\r\n','\n')!=value.replace('\r\n','\n'):
            changed.append(rel);patch+=difflib.unified_diff(original.replace('\r\n','\n').splitlines(True),value.replace('\r\n','\n').splitlines(True),fromfile=(reference or '(new)')+'/'+rel,tofile=version+'/'+rel)
    report={'format':'pbrd-template-generation-report','schema_version':1,'output':str(output),'generation_mode':'templates_from_json','baseline_required':False,'comparison_reference':reference,'inherited_modules':[],'counts':counts,'files':provenance,'changed_files':changed,'compile_status':'not_run','config_sha256':hashlib.sha256(json.dumps(config,ensure_ascii=False,sort_keys=True).encode('utf-8')).hexdigest(),'limitations':['Reviewed high-level forms include device power, battery charging, flash, crypto and CAN transceiver. Unsupported chip/bus combinations are rejected explicitly.','AC78428 / Keil 5.23 only; IAR/CMake adapters are not implemented.','No hardware validation; runtime baud/parity/range/rate are not automatically applied.']}
    diagnostics={}
    diagnostics['project-config.json']=json.dumps(config,ensure_ascii=False,indent=2)+'\n';diagnostics['comparison.patch']=''.join(patch)
    diagnostics['generation-report.json']=json.dumps(report,ensure_ascii=False,indent=2)+'\n'
    lines=['# '+version+' 模板生成对比','','本轮使用真实网页导出的 project-config.json，由正式模板生成；旧版本目录仅用于可选逐行对比，不提供生成配置。','','## 模块实例','','| 模块 | App | Boot |','| --- | ---: | ---: |']
    for module in sorted({m for target_counts in counts.values() for m in target_counts}):lines.append('| '+module+' | '+str(counts.get('app',{}).get(module,'—'))+' | '+str(counts.get('boot',{}).get(module,'—'))+' |')
    lines+=['','## ADC 与轴配置','']
    for item in config['board']['modules'].get('analog',[]):lines.append('- '+item['name']+'：'+item['params']['pin']+' / '+item['params']['channel'])
    for item in config['board']['modules'].get('axis',[]):lines.append('- '+item['name']+'：'+item['params']['driver']+' / '+item['params']['bus'])
    lines+=['','## 生成与维护边界','','- 高层实例生成覆盖 ADC、Axis、LED、CAN、EXT_INT、UART、MISC_CTRL、SWITCH、电源、充电、Flash、加密和 CAN 收发器。','- 器件及总线组合按已审核接口生成，未支持的组合明确报错；平台固定参数来自正式默认值文件。','- 构建脚本框架保留，仅更新 BRD_INCS；未移动或改名旧版本目录。','- 用户 includes/defines/code 区原样合并，生成区手改或删除带用户代码模块时停止更新。','- 当前工程适配为 AC78428 / Keil；IAR/CMake 尚待接入。','','逐行差异见 comparison.patch；模板和参数来源见 generation-report.json。编译结果见 compile-verification.json 与 build/*/verification-build.log，硬件运行未验证。','']
    diagnostics['COMPARISON.md']='\n'.join(lines)

    state_dir=tool/'.reports/generation'/output.name
    result=publish(output,generated,settings.get('mode','create'),state_dir,diagnostics);report.update(result)
    return report
