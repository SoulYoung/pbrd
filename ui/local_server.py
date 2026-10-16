"""Serve the editor/catalog and explicitly requested project generation on loopback."""
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlsplit
import argparse,json,mimetypes,webbrowser,sys,os,re,tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from generator.project_codegen import generate_project
from project_preset import project_preset
from folder_picker import choose_folder
from build_catalog import build_catalog
from build_preview import build_preview
from catalog_sources import read_enums
from project_context import project_context
from module_library import load_ui_modules as load_modules
from source_catalog import local_sync,source_settings,checked_settings
from project_scan import scan_project,write_report

CONTEXT=project_context()
ROOT=CONTEXT['project_root']
PBRD=CONTEXT['tool_root']

def platform_files():
    result={}
    for file in (PBRD/'platforms').glob('*.json'):
        data=json.loads(file.read_text(encoding='utf-8-sig'))
        if data.get('format')=='pbrd-platform' and data.get('schema_version')==1:
            result[data['mcu']]=file
    return result

class Handler(BaseHTTPRequestHandler):
    def send_data(self,data,mime='application/json; charset=utf-8',status=200):
        content=json.dumps(data,ensure_ascii=False).encode('utf-8') if isinstance(data,(dict,list)) else data
        self.send_response(status)
        self.send_header('Content-Type',mime)
        self.send_header('Content-Length',str(len(content)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        try:
            route=urlsplit(self.path).path
            if route=='/api/source-settings':
                self.send_data(source_settings(CONTEXT))
            elif route=='/api/project-preset':
                self.send_data(project_preset(CONTEXT))
            elif route=='/api/generation-dependencies':
                self.send_data(json.loads((PBRD/'platforms/ac78428-generation.json').read_text(encoding='utf-8-sig')).get('native_dependencies',{}))
            elif route=='/api/generation-defaults':
                self.send_data(json.loads((PBRD/'examples/HQT401_L30_template_default.json').read_text(encoding='utf-8-sig'))['codegen'])
            elif route=='/api/modules':
                self.send_data({'modules':load_modules(PBRD)})
            elif route=='/api/project-scan':
                self.send_data(scan_project(CONTEXT))
            elif route=='/api/context':
                self.send_data({key:str(value) for key,value in CONTEXT.items()})
            elif route=='/api/enums':
                self.send_data(read_enums(CONTEXT['enum_header']))
            elif route=='/api/platforms':
                self.send_data([{'mcu':mcu,'package':json.loads(path.read_text(encoding='utf-8-sig'))['package']} for mcu,path in sorted(platform_files().items())])
            elif route.startswith('/api/platform/'):
                name=route[len('/api/platform/'):]
                file=platform_files().get(name)
                if file is None:self.send_data({'error':'Platform resource JSON is missing'},status=404)
                else:self.send_data(json.loads(file.read_text(encoding='utf-8-sig')))
            elif route in ['/', '/board-config-preview.html']:
                self.send_data((PBRD/'board-config-preview.html').read_bytes(),'text/html; charset=utf-8')
            else:self.send_data({'error':'Not found'},status=404)
        except (OSError,ValueError,KeyError) as error:
            self.send_data({'error':str(error)},status=500)

    def do_POST(self):
        try:
            route=urlsplit(self.path).path
            if route not in ['/api/generate-project','/api/local-sync','/api/source-settings','/api/save-project-json','/api/select-json-directory']:
                self.send_data({'error':'Not found'},status=404)
                return
            origin=self.headers.get('Origin')
            if origin and origin!='http://'+self.headers.get('Host',''):
                self.send_data({'error':'Only the local editor may write files'},status=403)
                return
            size=int(self.headers.get('Content-Length','0'))
            if size<=0 or size>2*1024*1024:raise ValueError('JSON body must be between 1 byte and 2 MB')
            body=json.loads(self.rfile.read(size).decode('utf-8'))
            if route=='/api/local-sync':
                self.send_data(local_sync(CONTEXT,body['mcu'],body.get('settings')))
            elif route=='/api/select-json-directory':
                self.send_data(choose_folder(ROOT,body.get('initial','')))
            elif route=='/api/save-project-json':
                directory=body.get('directory');filename=body.get('filename');project=body.get('project')
                if not isinstance(directory,str) or not directory.strip():raise ValueError('Please set the JSON save directory')
                if not isinstance(filename,str) or not filename.lower().endswith('.json') or re.search(r'[<>:"/\\|?*\x00-\x1f]',filename) or filename.startswith('.'):raise ValueError('Invalid JSON filename')
                if not isinstance(project,dict) or project.get('format')!='pbrd-project' or project.get('schema_version')!=1:raise ValueError('Invalid project JSON')
                folder=Path(directory.strip())
                if not folder.is_absolute():folder=ROOT/folder
                folder=folder.resolve();folder.mkdir(parents=True,exist_ok=True);destination=folder/filename
                temporary=None
                try:
                    with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=folder,prefix='.pbrd-',suffix='.tmp',delete=False) as stream:
                        temporary=Path(stream.name);stream.write(json.dumps(project,ensure_ascii=False,indent=2)+'\n')
                    os.replace(temporary,destination)
                finally:
                    if temporary is not None and temporary.exists():temporary.unlink()
                self.send_data({'path':str(destination)})
            elif route=='/api/source-settings':
                settings=checked_settings(CONTEXT,body)
                (PBRD/'ui/source-settings.json').write_text(json.dumps(settings,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
                self.send_data(settings)
            else:
                report=generate_project(CONTEXT,body)
                self.send_data({'output':report['output'],'report':str(Path(report['report_directory'])/'generation-report.json'),'counts':report['counts']})
        except (OSError,ValueError,KeyError,TypeError) as error:
            self.send_data({'error':str(error)},status=400)

    def log_message(self,format,*args):pass

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=0)
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--project-root',help='Override the project directory')
    parser.add_argument('--check',action='store_true',help='Validate required data without starting a server')
    args=parser.parse_args()
    CONTEXT=project_context(args.project_root)
    ROOT=CONTEXT['project_root']
    if args.check:
        try:
            catalog=read_enums(CONTEXT['enum_header'])
            platforms=platform_files()
            if not platforms:raise ValueError('No platform JSON files found')
            print('Project:',ROOT)
            print('Enum header:',CONTEXT['enum_header'])
            print('Enum entries:',len(catalog['enum_catalog']))
            print('Platforms:',', '.join(sorted(platforms)))
            print('Editor ready. ADC/Axis/bus generation available; maintained templates generate from JSON.')
        except (OSError,ValueError,KeyError) as error:
            parser.exit(1,'Check failed: '+str(error)+'\n')
        parser.exit(0)
    build_catalog(CONTEXT)
    build_preview()
    report=scan_project(CONTEXT)
    write_report(CONTEXT,report)
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    url='http://127.0.0.1:'+str(server.server_port)+'/'
    print("PBRD v"+(PBRD/"VERSION").read_text(encoding="utf-8").strip(),flush=True)
    print(url,flush=True)
    print("Keep this window open. Open the URL above if the browser did not start. Ctrl+C stops the service.",flush=True)
    if not args.no_browser:webbrowser.open(url)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
