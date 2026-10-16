"""Compile generated projects in place, with SDK publication disabled in temporary copies."""
from pathlib import Path
import xml.etree.ElementTree as ET
import subprocess,json,argparse,sys,re
parser=argparse.ArgumentParser();parser.add_argument('--uv4',required=True);parser.add_argument('--board',default='product/src/brd/r01v02');args=parser.parse_args()
board=Path(args.board).resolve();results=[]
state=Path(__file__).resolve().parents[1]/'.reports/generation'/board.name
state.mkdir(parents=True,exist_ok=True)
for source in sorted(board.glob('build/*/brd.uvprojx')):
 build_state=state/'build'/source.parent.name;build_state.mkdir(parents=True,exist_ok=True)
 tree=ET.parse(source)
 for node in tree.getroot().iter():
  if node.tag in ['OutputDirectory','ListingPath']:
   directory=build_state/('release' if node.tag=='OutputDirectory' else 'listings');directory.mkdir(exist_ok=True);node.text=str(directory)+'\\'
 for node in tree.getroot().iter():
  if node.tag in ['RunUserProg1','RunUserProg2']:node.text='0'
 test=source.with_name('brd.verification.uvprojx');tree.write(test,encoding='utf-8',xml_declaration=True)
 log=build_state/'verification-build.log'
 try:
  startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
  run=subprocess.run([args.uv4,'-r',str(test),'-j0','-o',str(log)],cwd=source.parent,startupinfo=startup,timeout=120)
  content=log.read_bytes() if log.exists() else b''
  try:message=content.decode('utf-8-sig')
  except UnicodeDecodeError:message=content.decode('gb18030',errors='replace')
  message=message.replace('\r\n','\n').replace('\r','')
  log.write_text(message,encoding='utf-8')
  result={'project':str(source),'exit_code':run.returncode,'log':str(log),'publication_disabled':True,'passed':run.returncode==0 and bool(re.search(r'0 Error\(s\), 0 Warning\(s\)',message))}
  results.append(result);print(json.dumps(result),flush=True);print(message[-8000:],flush=True)
 finally:
  for temporary in source.parent.glob('brd.verification.*'):
   if temporary.is_file():temporary.unlink()
report=state/'compile-verification.json';report.write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

passed=bool(results) and all(r['passed'] for r in results)
report_path=state/'generation-report.json'
if report_path.exists():
 data=json.loads(report_path.read_text(encoding='utf-8'));data['compile_status']='passed_'+'_and_'.join(source.parent.name for source in sorted(board.glob('build/*/brd.uvprojx')))+'_zero_errors_zero_warnings' if passed else 'failed';data['compile_verification']='compile-verification.json';report_path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
if not passed:sys.exit(1)
