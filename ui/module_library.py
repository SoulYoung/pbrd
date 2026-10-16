"""Declarative module library. No project code is executed while scanning."""
from pathlib import Path
import json,re

FIELD_TYPES={'text','num','bool','select','gpio','adc','channel','signal','bus'}

def load_modules(tool_root):
    result=[]
    for file in sorted((Path(tool_root)/'modules').glob('*.json')):
        x=json.loads(file.read_text(encoding='utf-8-sig'))
        if x.get('format')!='pbrd-module' or x.get('schema_version')!=1:
            raise ValueError('Unsupported module definition: '+str(file))
        if x.get('id')!=file.stem or not re.fullmatch(r'[a-z][a-z0-9_]*',x['id']):
            raise ValueError('Module id must match filename: '+str(file))
        if not isinstance(x.get('name'),str) or x.get('configuration_mode') not in ['instances','platform']:
            raise ValueError('Invalid module name/mode: '+x['id'])
        keys=set()
        for f in x.get('fields',[]):
            if f.get('type') not in FIELD_TYPES or not isinstance(f.get('label'),str) or not re.fullmatch(r'[a-z][a-z0-9_]*',f.get('key','')) or f['key'] in keys:
                raise ValueError('Invalid field: '+x['id'])
            keys.add(f['key'])
            if 'value' not in f or not isinstance(f.get('opts'),list):
                raise ValueError('Missing field default/options: '+x['id'])
        for dep in x.get('dependencies',[]):
            if not re.fullmatch(r'(?:brd|drv|per|hal|idp)\.[a-z0-9_.]+',dep):
                raise ValueError('Invalid dependency: '+x['id'])
        for impl in x.get('implementations',[]):
            if not isinstance(impl.get('value'),str) or not isinstance(impl.get('source_globs'),list):
                raise ValueError('Invalid implementation: '+x['id'])
            for pattern in impl['source_globs']:
                if not pattern.startswith('product/') or '..' in Path(pattern).parts:
                    raise ValueError('Source pattern outside project: '+pattern)
        result.append(x)
    if not result:
        raise ValueError('Module library is empty')
    return result


def load_ui_modules(tool_root):
    """Apply editor-only forms without changing the source generator's module schema."""
    result=load_modules(tool_root)
    file=Path(tool_root)/'ui/frontend-fields.json'
    overrides=json.loads(file.read_text(encoding='utf-8-sig')) if file.is_file() else {}
    for module in result:module.update(overrides.get(module['id'],{}))
    return result
