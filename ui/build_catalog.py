"""Build an offline data snapshot from current platform JSON and project sources."""
from pathlib import Path
import json,re
from catalog_sources import read_enums
from project_context import project_context
from module_library import load_ui_modules as load_modules
from source_catalog import local_sync,source_settings
from project_scan import scan_project

def build_catalog(context=None):
    context=context or project_context()
    
    root=context['project_root']
    tool=context['tool_root']
    enums=read_enums(context['enum_header'])
    platforms={}
    drivers={}
    for file in sorted((tool/'platforms').glob('*.json')):
        data=json.loads(file.read_text(encoding='utf-8-sig'))
        if data.get('format')!='pbrd-platform' or data.get('schema_version')!=1:
            continue
        mcu=data['mcu']
        platforms[mcu]=data
        sources=root/'product/src/drv'/mcu
        drivers[mcu]=sorted({p.stem[4:] for p in sources.glob('drv_*.c')}) if sources.is_dir() else data['drivers']
    if not platforms:
        raise ValueError('No platform JSON resources found')
    first=next(iter(platforms))
    try:
        enum_source=context['enum_header'].relative_to(root).as_posix()
    except ValueError:
        enum_source=context['enum_header'].name
    defaults=json.loads((tool/'examples/HQT401_L30_template_default.json').read_text(encoding='utf-8-sig'))
    rules=json.loads((tool/'platforms/ac78428-generation.json').read_text(encoding='utf-8-sig'))
    live=local_sync(context,first)
    drivers[first]=live['drivers']
    platforms[first]=live['platform']
    snapshot={'live_sources':live,'source_settings':source_settings(context),'product_catalog':live['products']['products'],'generation_dependencies':rules.get('native_dependencies',{}),'generation_defaults':defaults['codegen'],'enum_catalog':live['enums']['enum_catalog'],'source_hash':enums['source_hash'],
              'enum_source':enum_source,'platforms':platforms,'drivers':drivers,
              'sample_times':platforms[first]['sample_times'],'module_library':live['module_library'],'project_scan':scan_project(context)}
    (tool/'ui/platform-data.js').write_text('window.PBRD_DATA = '+json.dumps(snapshot,ensure_ascii=False,indent=2)+';\n',encoding='utf-8')
    print('Snapshot refreshed from platform JSON:',', '.join(platforms))

if __name__=='__main__':
    build_catalog()
