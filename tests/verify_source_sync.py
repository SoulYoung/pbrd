from pathlib import Path
import sys,tempfile,json,hashlib
sys.path.insert(0,str(Path('pbrd/ui').resolve()))
from project_context import project_context
from source_catalog import local_sync,source_settings,checked_settings
context=project_context();settings=source_settings(context)
with tempfile.TemporaryDirectory(prefix='pbrd-sync-') as tmp:
 root=Path(tmp);ctx={**context,'project_root':root}
 for key in ['version_header','enum_header']:
  dest=root/settings[key];dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes((context['project_root']/settings[key]).read_bytes())
 entry=settings['platforms']['ac78428']
 for kind,key in [('brd','brd_directory'),('drv','drv_directory')]:
  dest=root/entry[key];dest.mkdir(parents=True,exist_ok=True);(dest/(kind+'_new_demo'+('_ac78428' if kind=='brd' else '')+'.h')).write_text('// UTF-8 public interface\n',encoding='utf-8')
 x=local_sync(ctx,'ac78428',settings)
 assert 'new_demo' in x['pending_modules'] and 'new_demo' in x['drivers']
 assert x['products']['products'] and x['enums']['enum_catalog']
 print('PASS source catalogs and newly discovered public interfaces')
 old=(root/settings['enum_header']).read_text(encoding='utf-8-sig');(root/settings['enum_header']).write_text(old+'\nkBrdAnalogBaseIdSyncDemo = 990, ///< 同步测试电压\n',encoding='utf-8')
 y=local_sync(ctx,'ac78428',settings);assert any(e['name']=='同步测试电压' for e in y['enums']['enum_catalog']);print('PASS sync re-reads edited function header')
 bad=json.loads(json.dumps(settings));bad['version_header']='../outside.h'
 try:checked_settings(ctx,bad);raise AssertionError('path escape accepted')
 except ValueError:pass
 print('PASS source path validation')
