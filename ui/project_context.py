"""Resolve tool and project locations without machine-specific paths."""
from pathlib import Path
import json

TOOL_ROOT=Path(__file__).resolve().parents[1]

def project_context(project_root=None):
    file=TOOL_ROOT/'pbrd.config.json'
    config=json.loads(file.read_text(encoding='utf-8-sig')) if file.exists() else {}
    selected=Path(project_root) if project_root else TOOL_ROOT/str(config.get('project_root','..'))
    root=selected.resolve()
    def resolve_source(key,default):
        value=Path(str(config.get(key,default)))
        return value.resolve() if value.is_absolute() else (root/value).resolve()
    return {'tool_root':TOOL_ROOT,'project_root':root,
            'enum_header':resolve_source('enum_header','product/src/brd/base/def/brd_def_base.h'),
            'board_source_root':resolve_source('board_source_root','product/src/brd')}
