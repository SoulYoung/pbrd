"""Frontend-only live source catalogs; never execute discovered project code."""
from pathlib import Path
import copy,json,re,hashlib
from catalog_sources import read_enums
from module_library import load_ui_modules

def source_settings(context):
    return json.loads((context['tool_root']/'ui/source-settings.json').read_text(encoding='utf-8-sig'))

def checked_settings(context,settings):
    settings=copy.deepcopy(settings)
    if settings.get('schema_version')!=1 or not isinstance(settings.get('platforms'),dict):raise ValueError('Invalid source settings schema')
    def relative(value):
        if not isinstance(value,str) or not value or Path(value).is_absolute() or ':' in value or '..' in Path(value.replace('\\','/')).parts:raise ValueError('Source paths must be relative, without .. or drive letters')
        return value.replace('\\','/')
    for key in ['version_header','enum_header']:settings[key]=relative(settings[key])
    for mcu,entry in settings['platforms'].items():
        if not re.fullmatch(r'[a-zA-Z0-9_]+',mcu):raise ValueError('Invalid MCU name')
        for key in ['brd_directory','drv_directory','pin_file']:entry[key]=relative(entry[key])
    return settings

def read_products(path):
    raw=Path(path).read_bytes();text=raw.decode('utf-8-sig');products=[]
    clean=re.sub(r'/\*.*?\*/','',text,flags=re.S)
    for body in re.findall(r'\benum(?:\s+\w+)?\s*\{(.*?)\}',clean,re.S):
        if not re.search(r'\bkBrd_[Vv]ersionBase\b',body):continue
        for match in re.finditer(r'^\s*(kBrd_[Vv]ersion\w+)\s*(?:=\s*([^,\n]+))?\s*,?\s*(?://[/<]*\s*([^\n]*))?',body,re.M):
            enum,expression,comment=match.groups()
            if enum.lower().endswith(('versionbase','versionmax')):continue
            products.append({'enum':enum,'name':comment.strip() if comment else re.sub(r'^kBrd_[Vv]ersion','',enum),'value':(expression or '').strip()})
    if not products:raise ValueError('No product enum block containing kBrd_VersionBase in '+str(path))
    return {'products':products,'source':str(path),'source_hash':hashlib.sha256(raw).hexdigest()}

def public_modules(directory,mcu,kind):
    directory=Path(directory);result=[]
    if not directory.is_dir():raise ValueError('Source directory missing: '+str(directory))
    for file in sorted(directory.glob(kind+'_*.h')):
        name=file.stem[len(kind)+1:]
        # Configuration headers belong to their driver, not separate modules.
        if kind=='drv' and name.endswith('_cfg'):continue
        if kind=='brd':
            name=re.sub('_'+re.escape(mcu)+r'(?:_boot)?$','',name)
        if not re.fullmatch(r'[a-z][a-z0-9_]*',name):continue
        result.append({'id':name,'header':str(file),'status':'public_header'})
    return result

def local_sync(context,mcu,settings=None):
    settings=checked_settings(context,settings or source_settings(context))
    if mcu not in settings['platforms']:raise ValueError('Configure source paths for MCU '+mcu+' first')
    root=context['project_root'];tool=context['tool_root'];entry=settings['platforms'][mcu]
    enums=read_enums(root/settings['enum_header']);products=read_products(root/settings['version_header'])
    platform=json.loads((tool/entry['pin_file']).read_text(encoding='utf-8-sig'))
    if platform.get('format')!='pbrd-platform' or platform.get('mcu')!=mcu:raise ValueError('Pin JSON does not match selected MCU')
    boards=public_modules(root/entry['brd_directory'],mcu,'brd');drivers=public_modules(root/entry['drv_directory'],mcu,'drv')
    modules=load_ui_modules(tool);known={m['id'] for m in modules}
    pending=[]
    for item in boards:
        if item['id'] not in known:
            module={'format':'pbrd-module','schema_version':1,'id':item['id'],'name':item['id'],'configuration_mode':'platform','configuration_status':'discovered','fields':[],'dependencies':[],'implementations':[],'notes':'本地同步发现对外头文件；配置表单尚待补充。','sources':{'public_header':item['header']}}
            modules.append(module);known.add(item['id']);pending.append(item['id'])
    platform['drivers']=[d['id'] for d in drivers]
    return {'settings':settings,'mcu':mcu,'platform':platform,'platforms':[{'mcu':name,'package':platform.get('package','') if name==mcu else ''} for name in settings['platforms']],
            'enums':enums,'products':products,'module_library':{'modules':modules},'public_modules':boards,'drivers':platform['drivers'],'pending_modules':pending,
            'sources':{'enum_header':settings['enum_header'],'version_header':settings['version_header'],**entry}}
