"""Publish source and tool-side state together; preserve user regions and rollback failures."""
from pathlib import Path
import os,json,tempfile,shutil,hashlib,time
from generator.user_sections import merge,sections,digest
MANIFEST='.pbrd-manifest.json'
DIAGNOSTICS={'generation-report.json','project-config.json','comparison.patch','COMPARISON.md','compile-verification.json'}

def read(path):return path.read_bytes().decode('utf-8-sig')

def replace(source,destination):
    for attempt in range(20):
        try:
            os.replace(source,destination)
            break
        except PermissionError:
            if attempt==19:raise
            time.sleep(0.1)

def cleanup(directory):
    for attempt in range(20):
        try:
            shutil.rmtree(directory)
            break
        except PermissionError:
            if attempt==19:raise
            time.sleep(0.1)

def publish(output,files,mode,state_dir=None,state_files=None):
    output=Path(output).resolve();state_dir=Path(state_dir).resolve() if state_dir else output
    output.parent.mkdir(parents=True,exist_ok=True)
    lock=output.parent/('.pbrd-generate-'+output.name+'.lock')
    try:descriptor=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError:raise ValueError('Generation already in progress (or recovery lock remains): '+str(output))
    try:
        os.close(descriptor)
        return _publish(output,files,mode,state_dir,state_files or {})
    finally:lock.unlink()

def _publish(output,files,mode,state_dir,state_files):
    existed=output.exists();external=state_dir!=output
    if existed and mode!='regenerate':raise ValueError('Output exists; choose regenerate explicitly: '+str(output))
    previous={};old_manifest=output/MANIFEST;manifest_file=state_dir/MANIFEST
    selected=manifest_file if manifest_file.is_file() else old_manifest
    if selected.is_file():
        saved=json.loads(read(selected))
        if saved.get('output',str(output))!=str(output):raise ValueError('Generation state belongs to another output directory')
        previous=saved['files']
    legacy=False
    if existed and not previous and (output/'generation-report.json').is_file():
        report=json.loads(read(output/'generation-report.json'))
        if report.get('format')=='pbrd-project-generation-report':
            legacy=True
            for rel in report.get('files',{}):
                path=output/rel
                if path.is_file():previous[rel]={'generated_digest':digest(read(path)) if rel.endswith(('.c','.h')) else None,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    candidate={};preserved=[]
    for rel,content in files.items():
        destination=(output/rel).resolve()
        if output not in destination.parents:raise ValueError('Invalid generated path: '+rel)
        if destination.is_file() and rel.endswith(('.c','.h')):
            original=read(destination)
            if rel in previous and digest(original)!=previous[rel]['generated_digest']:raise ValueError('Manual changes outside user region: '+rel)
            if rel not in previous and not sections(original) and original.replace('\r\n','\n')!=content.replace('\r\n','\n'):
                raise ValueError('Unmanaged existing source needs explicit migration: '+rel)
            content=merge(content,original)
            if any(v.strip() for v in sections(original).values()):preserved.append(rel)
        candidate[rel]=content
    obsolete=[];state_files=dict(state_files)
    for rel in previous:
        if rel in candidate:continue
        path=output/rel
        if path.is_file():
            if rel.endswith(('.c','.h')):
                original=read(path)
                if any(v.strip() for v in sections(original).values()) or digest(original)!=previous[rel]['generated_digest']:raise ValueError('Removed module contains user/manual code: '+rel)
            elif rel not in DIAGNOSTICS and hashlib.sha256(path.read_bytes()).hexdigest()!=previous[rel]['sha256']:
                raise ValueError('Removed generated file was edited: '+rel)
            if external and rel not in state_files:state_files['previous-output/'+rel]=path.read_bytes()
            obsolete.append(rel)
    if external:
        for rel in DIAGNOSTICS:
            path=output/rel
            if path.is_file() and rel not in obsolete:
                obsolete.append(rel)
                if rel not in state_files:state_files[rel]=path.read_bytes()
        if old_manifest.is_file():obsolete.append(MANIFEST)
    result={'preserved_user_files':preserved,'removed_files':obsolete,'legacy_manifest_imported':legacy,'report_directory':str(state_dir)}
    reports=state_files if external else candidate
    if 'generation-report.json' in reports:
        report=json.loads(reports['generation-report.json']);report.update(result);reports['generation-report.json']=json.dumps(report,ensure_ascii=False,indent=2)+'\n'
    manifest={'format':'pbrd-generated-files','schema_version':2,'output':str(output),'files':{}}
    stage=Path(tempfile.mkdtemp(prefix='.pbrd-candidate-',dir=str(output.parent))).resolve()
    undo={};written=[];removed=[]
    try:
        destinations={}
        for rel,content in candidate.items():
            data=content.replace('\r\n','\n').replace('\n','\r\n').encode('utf-8') if rel.endswith('.bat') else content.encode('utf-8')
            destinations[output/rel]=data
            manifest['files'][rel]={'sha256':hashlib.sha256(data).hexdigest(),'generated_digest':digest(content) if rel.endswith(('.c','.h')) else None}
        if external:
            for rel,content in state_files.items():
                path=(state_dir/rel).resolve()
                if state_dir not in path.parents:raise ValueError('Invalid tool state path: '+rel)
                destinations[path]=content if isinstance(content,bytes) else content.encode('utf-8')
        destinations[manifest_file]=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
        for index,(path,data) in enumerate(destinations.items()):
            staged=stage/str(index);staged.write_bytes(data)
        output.mkdir(parents=True,exist_ok=True)
        for index,path in enumerate(destinations):
            undo[path]=path.read_bytes() if path.is_file() else None;path.parent.mkdir(parents=True,exist_ok=True)
            replace(stage/str(index),path);written.append(path)
        for rel in obsolete:
            path=output/rel;undo[path]=path.read_bytes();path.unlink();removed.append(path)
    except BaseException:
        for path in reversed(written+removed):
            if undo[path] is None:
                if path.exists():path.unlink()
            else:path.write_bytes(undo[path])
        raise
    finally:
        assert stage.parent==output.parent.resolve() and stage.name.startswith('.pbrd-candidate-')
        cleanup(stage)
    return result
