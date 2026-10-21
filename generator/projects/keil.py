"""Keil library project assembly consumes generated files and an explicit member list."""
from pathlib import Path
import os,re,xml.etree.ElementTree as ET
OWNERS={'per_fram_at24_ex.c':'flash','per_mmc_spi_sd_ex.c':'flash','per_fee.c':'flash','per_hsm_ciu98b_ex.c':'crypto','per_rtc_bm8563_ex.c':'ext_rtc','per_can_trx_tja1445.c':'can_trx','idp_enum_iic_ex.c':'flash'}
def relative_path(path,directory):
    try:value=os.path.relpath(path,directory)
    except ValueError:value=str(path)
    return value.replace('/',chr(92))

def assemble(context,layout,target,effective,generated,axis_sources,output,version):
    tool=context['tool_root'];root=context['project_root'];folder=layout['targets'][target]['folder'];project_rel='build/'+folder+'/brd.uvprojx';project_dir=output/'build'/folder
    tree=ET.parse(tool/'templates'/layout['projects'][target]);xml=tree.getroot();members=[]
    for member in layout['targets'][target]['members']:
        module=member['module']
        if member['generated']:
            if member['path'] not in generated:continue
            absolute=output/member['path']
        else:
            if module and module not in effective:continue
            owner=OWNERS.get(Path(member['path']).name)
            if owner and 'brd.'+owner not in effective:continue
            absolute=root/member['path']
            if not absolute.is_file():raise ValueError('Missing project source: '+str(absolute))
        members.append((member['group'],absolute))
    if 'brd.axis' in effective:
        members.append(('src',output/folder/'src/brd_axis.c'))
        for source in axis_sources:
            if not (root/source).is_file():raise ValueError('Missing Axis driver: '+source)
            members.append(('per',root/source))
    for module,extension in layout.get('extensions',{}).items():
        if 'brd.'+module in effective:
            for source in extension.get('sources',[]):
                path=root/source
                if not path.is_file():raise ValueError('Missing '+module+' source: '+source)
                members.append(('per' if '/per/' in source else 'idp',path))
    for module,implementation in layout.get('implementation_sources',{}).items():
        if module in effective:
            for source in implementation['sources']:
                path=root/source
                if not path.is_file():raise ValueError('Missing implementation source: '+source)
                members.append(('per',path))
    seen=set()
    for group in xml.iter('Group'):
        name=group.findtext('GroupName');files=group.find('Files')
        if files is None:continue
        for category,file in members:
            if category!=name or str(file) in seen:continue
            seen.add(str(file));node=ET.SubElement(files,'File');ET.SubElement(node,'FileName').text=file.name;ET.SubElement(node,'FileType').text='1';ET.SubElement(node,'FilePath').text=relative_path(file,project_dir)
    for node in xml.iter('IncludePath'):
        entries=[]
        # Template paths are based on the standard board-version/build layout.
        template_dir=context['board_source_root']/'_template_version'/'build'/folder
        for entry in (node.text or '').split(';'):
            if not entry:continue
            original=(template_dir/entry.replace(chr(92),'/')).resolve()
            try:local=original.relative_to(template_dir.parents[1])
            except ValueError:pass
            else:original=output/local
            entries.append(relative_path(original,project_dir))
        if 'brd.axis' in effective:
            for path in [root/'product/src/per/axis/common']+[Path(root/s).parent for s in axis_sources]:
                entry=relative_path(path,project_dir)
                if entry not in entries:entries.append(entry)
        for module,extension in layout.get('extensions',{}).items():
            if 'brd.'+module in effective:
                for source in extension.get('sources',[]):
                    entry=relative_path((root/source).parent,project_dir)
                    if entry not in entries:entries.append(entry)
        for module,implementation in layout.get('implementation_sources',{}).items():
            if module in effective:
                for source in implementation['sources']:
                    entry=relative_path((root/source).parent,project_dir)
                    if entry not in entries:entries.append(entry)
        node.text=';'.join(entries)
    for node in xml.iter('UserProg1Name'):
        if node.text:node.text=re.sub(r'\br\d+v\d+\b',version,node.text,flags=re.I)
    # Keep the XML encoding declaration required by the uVision GUI.
    return project_rel,'<?xml version="1.0" encoding="UTF-8" standalone="no" ?>\n'+ET.tostring(xml,encoding='unicode')+'\n'
