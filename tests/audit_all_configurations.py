"""Compare all original App/Boot configuration graphs with actual generated output."""
from pathlib import Path
import re,json,sys,subprocess,difflib
TOOL=Path(__file__).resolve().parents[1];sys.path[:0]=[str(TOOL),str(TOOL/'ui')]
from generator.c_parser import declarations,mask,end_brace
ROOT=TOOL.parent;oldroot=ROOT/'product/src/brd/r01v02';newroot=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else TOOL/'.reports/code-review-20261020';compiler='D:/Keil/ARM/ARMCC/bin/armcc.exe'
def read(path):
 source=path.read_text(encoding='utf-8-sig');run=subprocess.run([compiler,'-E',str(path)],capture_output=True,check=True)
 values={d['name']:d['value'] for d in declarations(run.stdout.decode('utf-8-sig'))};return source,values
def normalize(v,values,source,key='',seen=None):
 seen=set() if seen is None else seen
 if isinstance(v,dict):
  value=dict(v)
  for field,group in list(value.items()):
   if group=='kDrvPortGroupMax':
    prefix=field[:-5] if field.endswith('group') else ''
    for suffix in ['pin','pin_mux','mux']:value.pop(prefix+suffix,None)
  return {k:normalize(x,values,source,k,seen) for k,x in value.items() if k not in ['dev_drv','dev_drv_parent','count','base_count','build_time'] and x not in [0,False,'NULL']}
 if isinstance(v,list):
  if key=='pins' and len(v)==5:return normalize(dict(zip(['pwr','rst','chk','scl','sda'],v)),values,source,key,seen)
  return [normalize(x,values,source,key,seen) for x in v]
 if isinstance(v,str):
  if re.fullmatch(r'(0x[0-9a-fA-F]+|\d+)[uUlL]*',v):return int(re.sub(r'[uUlL]+$','',v),0)
  ref=re.fullmatch(r'(?:\(void\*\))?&(\w+)(?:\[\(?([0-9]+)\)?\])?',v)
  if ref:
   name,index=ref.groups();token=(name,index)
   if key in ['mutex','mutex_cnt','event','bus_drv']:
    declaration=re.search(r'\b([A-Za-z_]\w*)[ \t]+'+re.escape(name)+r'\b',mask(source))
    if declaration:return {'resource_type':declaration[1],'index':int(index or 0)}
   if name in values and token not in seen:
    obj=values[name]
    if index is not None:
     if not isinstance(obj,list) or int(index)>=len(obj):return {'resource_index':int(index)}
     obj=obj[int(index)]
    return normalize(obj,values,source,key,seen|{token})
   return {'resource_index':int(index)} if index is not None else {'external':name}
  if key=='DoEnable' and v!='NULL':
   m=re.search(r'(?:static\s+)?void\s+'+re.escape(v)+r'\s*\(Bool\s+enable\)\s*\{',mask(source))
   if m:
    body=source[m.end():end_brace(mask(source),m.end()-1)-1]
    return re.sub(r'\s+','',mask(body))
 return v
def item_maps(values,source):
 result={}
 for name,rows in values.items():
  if isinstance(rows,list) and rows and all(isinstance(r,dict) and 'id' in r for r in rows):
   result[name]={str(r['id']):normalize(r,values,source) for r in rows}
 return result
results=[]
for before in sorted(oldroot.rglob('*cfg*.c')):
 rel=before.relative_to(oldroot);after=newroot/rel;entry={'path':rel.as_posix()}
 if not after.is_file():
  entry.update(status='not_generated',note='Boot XCU SPI is unselected in the user project JSON' if before.name=='brd_xcu_spi_cfg.c' else 'REVIEW missing output');results.append(entry);continue
 source,a=read(before);generated,b=read(after);left=item_maps(a,source);right=item_maps(b,generated);changes=[];added=[]
 for name,rows in left.items():
  if name not in right:changes.append({'array':name,'issue':'missing array'});continue
  for id,value in rows.items():
   if id not in right[name]:changes.append({'array':name,'id':id,'issue':'missing original item'});continue
   if value!=right[name][id]:
    diff=''.join(difflib.unified_diff(json.dumps(value,ensure_ascii=False,indent=2,sort_keys=True).splitlines(True),json.dumps(right[name][id],ensure_ascii=False,indent=2,sort_keys=True).splitlines(True),fromfile='original',tofile='generated'))
    changes.append({'array':name,'id':id,'diff':diff})
  added += [{'array':name,'id':id} for id in right[name].keys()-rows.keys()]
 if before.name.startswith('brd_common_cfg'):
  for name in ['g_drv_iic_cfgs','g_drv_spi_cfgs','g_brd_version_']:
   if normalize(a.get(name),a,source)!=normalize(b.get(name),b,generated):changes.append({'object':name,'before':a.get(name),'after':b.get(name)})
  for name in ['Brd_DiffInit','Brd_DiffDone','Brd_DiffOpen','Brd_DiffClose']:
   def calls(text):
    clean=mask(text);m=re.search(r'void\s+'+name+r'\s*\(void\)\s*\{',clean);body=clean[m.end():end_brace(clean,m.end()-1)-1]
    return re.findall(r'\b((?:Brd_|TDrv)\w+)\s*\(',body)
   if calls(source)!=calls(generated):changes.append({'function':name,'before':calls(source),'after':calls(generated)})
 if before.name=='brd_xcu_cfg.c':
  for name in ['g_drv_xcu_spi_cfg','g_brd_xcu_attr']:
   if normalize(a[name],a,source)!=normalize(b[name],b,generated):changes.append({'object':name,'before':a[name],'after':b[name]})
 confirmed=[d for d in changes if d.get('id')=='kBrd_ExtIntIdSw4' and before.name=='brd_ext_int_cfg.c']
 if confirmed:entry['confirmed_json_changes']=[{'id':'kBrd_ExtIntIdSw4','note':'User confirmed PD7 falling/falling; original PD27 rising/rising is intentionally not restored.'}];changes=[d for d in changes if d not in confirmed]
 entry.update(status='review' if changes else 'configuration_graph_match',differences=changes,added_items=added,original_item_counts={k:len(v) for k,v in left.items()},generated_item_counts={k:len(v) for k,v in right.items()});results.append(entry)
report=TOOL/'.reports/all-configuration-audit.json';report.write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for item in results:
 print(item['path'],item['status'],'differences',len(item.get('differences',[])),'added',item.get('added_items',[]))
 for d in item.get('differences',[]):print(json.dumps(d,ensure_ascii=True)[:1600])

assert not any(r["status"]=="review" for r in results),"Unreviewed configuration differences remain"
