"""Run before opening the editor or when switching project repositories."""
import argparse,json
from ui.project_context import project_context
# Support execution both as a root CLI and through the local server.
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/'ui'))
from project_scan import scan_project,write_report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Compare actual project sources with PBRD module support')
    parser.add_argument('--project-root')
    parser.add_argument('--no-write',action='store_true')
    args=parser.parse_args()
    context=project_context(args.project_root)
    report=scan_project(context)
    print(json.dumps(report['summary'],ensure_ascii=False))
    if not args.no_write:print('Report:',write_report(context,report))
