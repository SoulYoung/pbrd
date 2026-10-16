"""Inventory actual source files and compare them with module definitions."""
from pathlib import Path
import json,re,xml.etree.ElementTree as ET
from module_library import load_modules

IGNORED={'.git','__pycache__','build','release','node_modules'}

def scan_project(context):
    root=context['project_root'];tool=context['tool_root']
    specs=load_modules(tool)
    def relative(path):return path.relative_to(root).as_posix()
    def match(pattern,mcu='ac78428'):
        return sorted(relative(p) for p in root.glob(pattern.replace('{mcu}',mcu)) if p.is_file())
    implementations={}
    per_root=root/'product/src/per'
    if per_root.is_dir():
        for file in sorted(per_root.rglob('*')):
            if not file.is_file() or file.suffix.lower() not in ['.c','.h']:continue
            parts=file.relative_to(per_root).parts
            if any(p in IGNORED for p in parts) or 'common' in parts:continue
            family=parts[0]
            variant=parts[1] if len(parts)>2 else family
            if len(parts)==2 and family=='ic_card':
                found=re.fullmatch(r'per_ic_card_(sle\d+)(?:_ex)?',file.stem)
                if not found:continue
                variant=found[1]
            key='per.'+family+'.'+variant
            impl=implementations.setdefault(key,{'id':key,'category':family,'variant':variant,'files':[],'defined_by':[]})
            impl['files'].append(relative(file))
    driver_data={}
    drv_root=root/'product/src/drv'
    if drv_root.is_dir():
        for platform in sorted(drv_root.iterdir()):
            if platform.is_dir():driver_data[platform.name]=sorted(file.stem[4:] for file in platform.glob('drv_*.c'))
    availability={}
    for spec in specs:
        statuses={}
        for impl in spec.get('implementations',[]):
            files=sorted({path for pattern in impl['source_globs'] for path in match(pattern)})
            statuses[impl['value']]={'module':impl.get('module'),'status':'available' if any(p.endswith('.c') for p in files) else 'headers_only' if files else 'missing','files':files}
            key=impl.get('module')
            if key in implementations:implementations[key]['defined_by'].append(spec['id'])
        availability[spec['id']]=statuses
    known={key for spec in specs for impl in spec.get('implementations',[]) for key in [impl.get('module')] if key}
    for key,impl in implementations.items():
        impl['support']='defined' if key in known else 'unregistered'
        impl['source_status']='source_present' if any(p.endswith('.c') for p in impl['files']) else 'headers_only'
    projects=[];board_catalog={};missing=[]
    board_root=context['board_source_root']
    if board_root.is_dir():
        for source in sorted(board_root.glob('*/ac*/src/brd_*.c')):
            key=source.stem[4:]
            record=board_catalog.setdefault(key,{'id':key,'defined':any(s['id']==key for s in specs),'files':[]})
            record['selection_mode']=next((s.get('selection_mode','selectable') for s in specs if s['id']==key),'unreviewed')
            record['files'].append(relative(source))
        for file in sorted(board_root.glob('*/build/*/*.uvprojx')):
            try:
                xml=ET.parse(file).getroot();entry={'file':relative(file),'sources':[],'missing_sources':[],'missing_include_directories':[]}
                for node in xml.iter('FilePath'):
                    if node.text:
                        candidate=(file.parent/node.text.replace('\\','/')).resolve()
                        entry['sources'].append(node.text)
                        if not candidate.is_file():entry['missing_sources'].append(node.text)
                for node in xml.iter('IncludePath'):
                    for text in (node.text or '').split(';'):
                        if text and '$' not in text and not (file.parent/text.replace('\\','/')).is_dir():entry['missing_include_directories'].append(text)
                projects.append(entry)
            except (ET.ParseError,OSError):continue
    new_per=[impl for impl in implementations.values() if impl['support']=='unregistered']
    new_brd=[record for record in board_catalog.values() if not record['defined']]
    return {'format':'pbrd-project-scan','schema_version':1,'project_root':str(root),
            'drivers':driver_data,'per_implementations':list(implementations.values()),
            'module_implementations':availability,'board_modules':list(board_catalog.values()),
            'keil_projects':projects,'unregistered_per':new_per,'unregistered_brd':new_brd,
            'summary':{'defined_modules':len(specs),'per_implementations':len(implementations),'unregistered_per':len(new_per),'unregistered_brd':len(new_brd)}}

def write_report(context,report):
    out=context['tool_root']/'.reports';out.mkdir(exist_ok=True)
    (out/'project-scan.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# 项目模块接入清单','','扫描仅识别实际文件，不推断未审核的接口。扩展规则见 docs/ADDING_MODULES.md。','', '## 未收录的外设实现','']
    for impl in report['unregistered_per']:
        lines+=['- '+impl['id']]+['  - '+p for p in impl['files']]
    if not report['unregistered_per']:lines+=['无。']
    lines+=['','## 未收录的板级模块','']
    for record in report['unregistered_brd']:lines+=['- '+record['id']]+['  - '+p for p in record['files']]
    if not report['unregistered_brd']:lines+=['无。']
    lines+=['','## 待核对工程引用','']
    for project in report['keil_projects']:
        if project['missing_sources'] or project['missing_include_directories']:
            lines+=['- '+project['file']]+['  - 源码缺失：'+p for p in project['missing_sources']]+['  - Include 目录缺失：'+p for p in project['missing_include_directories']]
    (out/'MODULE_GAPS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return out
