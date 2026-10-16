"""Keep marked user text verbatim; malformed markers are fatal."""
import re,hashlib
BEGIN=re.compile(r'/\*\*\*\*\* User ([A-Za-z0-9_ .:-]+) begin \*\*\*\*\*/')
def sections(source):
    result={};matches=list(BEGIN.finditer(source))
    for match in matches:
        name=match[1];end='/***** User '+name+' end *****/'
        if name in result or source.count(end)!=1:raise ValueError('Duplicate or unpaired user section: '+name)
        finish=source.find(end,match.end())
        if finish<match.end():raise ValueError('Invalid user section order: '+name)
        value=source[match.end():finish]
        if BEGIN.search(value):raise ValueError('Nested user sections are not allowed')
        result[name]=value
    if len(re.findall(r'/\*\*\*\*\* User .+? end \*\*\*\*\*/',source))!=len(matches):raise ValueError('Unpaired user section end marker')
    return result
def merge(candidate,old):
    previous=sections(old);current=sections(candidate)
    lost=[k for k,v in previous.items() if v.strip() and k not in current]
    if lost:raise ValueError('Nonempty user sections would be lost: '+', '.join(lost))
    for name in current:
        if name in previous:
            pattern=re.compile(r'(/\*\*\*\*\* User '+re.escape(name)+r' begin \*\*\*\*\*/).*?(/\*\*\*\*\* User '+re.escape(name)+r' end \*\*\*\*\*/)',re.S)
            candidate=pattern.sub(lambda m:m[1]+previous[name]+m[2],candidate)
    return candidate
def digest(source):
    for name in sections(source):
        pattern=re.compile(r'(/\*\*\*\*\* User '+re.escape(name)+r' begin \*\*\*\*\*/).*?(/\*\*\*\*\* User '+re.escape(name)+r' end \*\*\*\*\*/)',re.S)
        source=pattern.sub(lambda m:m[1]+m[2],source)
    return hashlib.sha256(source.replace('\r\n','\n').encode('utf-8')).hexdigest()
def add(source,kind='code'):
    if not BEGIN.search(source):
        region='\n/***** User '+kind+' begin *****/\n\n/***** User '+kind+' end *****/\n\n'
        closing=source.rfind('#endif') if '#ifndef ' in source else -1
        source=source[:closing]+region+source[closing:] if closing>=0 else source.rstrip()+'\n'+region
    return source
