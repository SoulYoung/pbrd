"""Balanced initializer reader for explicit source → JSON import, not generation."""
import re
DECL=re.compile(r'\b(?:static\s+)?(?:const\s+)?([A-Za-z_]\w*)\s+([A-Za-z_]\w*)\s*(\[[^\]]*\])?\s*=\s*\{')
def mask(source):return re.sub(r'/\*.*?\*/|//[^\n]*',lambda m:' '*len(m.group()),source,flags=re.S)
def end_brace(source,start):
    depth=0
    for i in range(start,len(source)):
        if source[i]=='{':depth+=1
        elif source[i]=='}':
            depth-=1
            if depth==0:return i+1
    raise ValueError('Unbalanced C initializer')
def split(source):
    result=[];start=0;depth=0
    for i,ch in enumerate(source):
        if ch in '({[':depth+=1
        elif ch in ')}]':depth-=1
        elif ch==',' and depth==0:
            if source[start:i].strip():result.append(source[start:i].strip())
            start=i+1
    if source[start:].strip():result.append(source[start:].strip())
    return result
def parse(source):
    source=mask(source).strip()
    if source.startswith('{') and source.endswith('}'):
        parts=split(source[1:-1])
        if parts and all(re.match(r'^\.\s*\w+\s*=',p) for p in parts):return {re.match(r'^\.\s*(\w+)\s*=',p)[1]:parse(p.split('=',1)[1]) for p in parts}
        result=[];conditions=[]
        for part in parts:
            prefix=part[:part.find('{')] if '{' in part else part
            for directive,macro in re.findall(r'^\s*#(ifdef|endif)\s*(\w*)',prefix,re.M):
                if directive=='ifdef':conditions.append(macro)
                elif conditions:conditions.pop()
                else:raise ValueError('Unbalanced initializer preprocessor')
            clean=re.sub(r'^\s*#(?:ifdef|endif)[^\n]*(?:\n|$)','',part,flags=re.M).strip()
            if clean:
                value=parse(clean)
                for condition in reversed(conditions):value={'$ifdef':condition,'value':value}
                result.append(value)
        return result
    if source in ['True','False']:return source=='True'
    if re.fullmatch(r'-?\d+',source):return int(source)
    return source
def declarations(source):
    clean=mask(source);result=[]
    for match in DECL.finditer(clean):
        end=end_brace(clean,match.end()-1)
        result.append({'type':match[1],'name':match[2],'array':bool(match[3]),'start':match.end()-1,'end':end,'value':parse(source[match.end()-1:end])})
    return result
