"""C formatting shared by all module adapters."""
import re,math
IDENTIFIER=re.compile(r'[A-Za-z_]\w*\Z')
def identifier(value):
    if not isinstance(value,str) or not IDENTIFIER.fullmatch(value):raise ValueError('Invalid C identifier: '+str(value))
    return value
def scalar(value):
    if isinstance(value,bool):return 'True' if value else 'False'
    if isinstance(value,(int,float)) and math.isfinite(value):return str(value)
    if isinstance(value,str) and value and re.fullmatch(r'[A-Za-z0-9_\s.&*+\-/|~()<>,\[\]]+',value) and not any(x in value for x in ['//','/*','*/']):return value
    raise ValueError('Unsupported C expression: '+str(value))
def initializer(value,indent=0):
    if not isinstance(value,(dict,list)):return scalar(value)
    lines=['{'];pairs=value.items() if isinstance(value,dict) else [(None,v) for v in value]
    keys=[str(k) for k in value] if isinstance(value,dict) else [];width=max([len(k) for k in keys]+[0])+2
    for key,entry in pairs:
        array=value.get('item' if key=='count' else 'base') if isinstance(value,dict) and key in ['count','base_count'] else None
        if isinstance(array,str) and IDENTIFIER.fullmatch(array) and array!='NULL':entry='sizeof('+array+') / sizeof('+array+'[0])'
        if isinstance(entry,dict) and '$ifdef' in entry:
            lines+=['#ifdef '+identifier(entry['$ifdef']),' '*(indent+4)+initializer(entry['value'],indent+4)+',','#endif']
            continue
        prefix=' '*(indent+4)+(('.'+identifier(key)).ljust(width)+'= ' if key is not None else '')
        if isinstance(entry,(dict,list)):
            if key is not None:lines.append(prefix.rstrip());lines.append(' '*(indent+4)+initializer(entry,indent+4)+',')
            else:lines.append(prefix+initializer(entry,indent+4)+',')
        else:lines.append(prefix+scalar(entry)+',')
    lines.append(' '*indent+'}')
    return '\n'.join(lines)
def port(pin):
    m=re.fullmatch(r'P([A-Z])(\d+)',pin)
    if not m:raise ValueError('Invalid pin: '+str(pin))
    return 'kDrvPortGroup'+m[1],'kDrvPortPin'+m[2]
def macro(module,enum,family):
    prefix=next((p for p in ['kBrd_'+family+'Id','kBrd'+family+'Id'] if enum.startswith(p)),None)
    suffix=enum[len(prefix):] if prefix else enum
    return 'BRD_'+module.upper()+'_ID_'+re.sub(r'(?<=[a-z0-9])(?=[A-Z])','_',suffix).upper()


def address_expression(value,default_macro,default,macro_name,bits=7):
    if value in [None,'',default_macro]:return default_macro,''
    text=re.sub(r'[uUlL]+$','',str(value));number=int(text,0)
    if not 0<=number<(1<<bits):raise ValueError('Address out of range: '+str(value))
    if number==default:return default_macro,''
    name=identifier(macro_name)
    return name,'#define '+name+' 0x'+format(number,'02X')+'U\n'
