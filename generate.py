"""Generate directly from the project's editor-exported JSON."""
import argparse,json,sys
from pathlib import Path
from ui.project_context import project_context
sys.path.insert(0,str(Path(__file__).resolve().parent/'ui'))
from generator.project_codegen import generate_project
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--project-root');parser.add_argument('--config',required=True);parser.add_argument('--output')
    args=parser.parse_args()
    try:
        config=json.loads(Path(args.config).read_text(encoding='utf-8-sig'))
        report=generate_project(project_context(args.project_root),config,args.output)
        print('Generated:',report['output']);print('JSON counts:',report['counts'])
    except (OSError,ValueError,KeyError) as error:parser.exit(1,'Generation failed: '+str(error)+'\n')
