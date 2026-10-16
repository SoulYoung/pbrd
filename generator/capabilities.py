"""List reviewed platform capability macros, including inactive alternatives."""
import re

def render(source,capabilities):
    if not capabilities:return source
    active=set(re.findall(r'^\s*#define\s+(BRD_[A-Z0-9_]+)\b',source,re.M))
    prefix=lambda name:'_BUS_' in name or '_DEV_' in name
    names=set(capabilities)|{name for name in active if prefix(name)}
    lines=source.splitlines();kept=[];insertion=None
    for line in lines:
        flag=re.match(r'^\s*(?://\s*)?#define\s+(BRD_[A-Z0-9_]+)\s*$',line)
        heading=line.strip() in ['/// -------使用到的总线配置-------','/// -------使用到的设备配置-------']
        if heading or flag and flag[1] in names:
            if insertion is None:insertion=len(kept)
            continue
        kept.append(line)
    if insertion is None:
        marker=next((n for n,line in enumerate(kept) if line.strip()=='/***** User defines end *****/'),None)
        insertion=marker+1 if marker is not None else 0
    block=[]
    for group,title in [('_BUS_','/// -------使用到的总线配置-------'),('_DEV_','/// -------使用到的设备配置-------')]:
        selected=sorted(name for name in names if group in name)
        if selected:
            block+=[title]+[('#define ' if name in active else '// #define ')+name for name in selected]+['']
    kept[insertion:insertion]=block
    return re.sub(r'\n{3,}','\n\n','\n'.join(kept))+'\n'
