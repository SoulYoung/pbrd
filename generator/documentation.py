"""Project-specific row comments and hardware checklists, derived from the input JSON."""
import re
from pathlib import Path
from generator.c_parser import declarations,end_brace

def pins_in(value):
    result=[]
    if isinstance(value,dict):
        for key,group in value.items():
            if isinstance(group,str) and re.fullmatch(r'kDrvPortGroup[A-Z]',group):
                pin=value.get(key[:-5]+'pin' if key.endswith('group') else 'pin')
                if isinstance(pin,str) and re.fullmatch(r'kDrvPortPin\d+',pin):result.append('P'+group[-1]+pin[len('kDrvPortPin'):])
            result+=pins_in(group)
    elif isinstance(value,list):
        for item in value:result+=pins_in(item)
    return list(dict.fromkeys(result))

def item_label(item):
    a=item['params']
    return item['name']+(', '+a['channel'] if isinstance(a.get('channel'),str) and a['channel'].startswith('ADC') else '')

def annotate(text,labels):
    # Macro calls get a short trailing comment; full structs use the original
    # opening-brace comment style. Device/ID mapping arrays are left alone.
    edits=[]
    for d in declarations(text):
        names=labels.get(d['name'])
        if not names or not isinstance(d['value'],list):continue
        start=d['start']+1;depth=0;row=0
        for index in range(start,d['end']-1):
            char=text[index]
            if char in '({[':depth+=1
            elif char in ')}]':depth-=1
            elif char==',' and depth==0:
                part=text[start:index];offset=len(part)-len(part.lstrip())
                if row<len(names) and names[row] and part.strip() and not part.lstrip().startswith('#'):
                    label=names[row].replace('\n',' ').replace('\r',' ').replace('\\','/').strip()
                    if part.lstrip().startswith('{'):edits.append((start+offset+1,'   ///< '+label))
                    else:edits.append((index+1,'    ///< '+label))
                start=index+1;row+=1
    for index,value in reversed(edits):text=text[:index]+value+text[index:]
    return text

def comments(module,items,values,definitions):
    if module=='pwr_ctrl':
        def label(item):
            a=item['params'];detail=a.get('pin') if a.get('control_mode')=='gpio' else a.get('control_ref')
            return item['name']+(', '+str(detail) if detail else '')
        return {'g_brd_pwr_ctrl_cfgs_':[label(i) for i in items if i['params'].get('power_kind')!='base'],'g_brd_pwr_ctrl_base_cfgs_':[label(i) for i in items if i['params'].get('power_kind')=='base']}
    if module=='bat_chg':
        labels=[]
        for item in items:
            a=item['params']
            labels += [item['name']+'使能, '+(a.get('control_ref') if a.get('enable_mode')=='power' else a.get('enable_pin') or '未使用'),'充电完成, '+(a.get('done_pin') or '未使用'),'充电状态, '+(a.get('charging_pin') or '未使用')]
        return {'g_brd_bat_chg_cfg_':labels}
    physical={'analog':'g_drv_adc_ch_cfgs_','uart':'g_drv_uart_cfgs_','can':'g_drv_can_cfgs_','led':'g_brd_led_cfg_','misc_ctrl':'g_brd_misc_ctrl_cfgs_','switch':'g_brd_switch_cfgs_','meter':'g_drv_psmu_ch_cfg_'}
    if not items or module not in physical:return {}
    labels=[]
    for item in items:
        a=item['params']
        if module in ['can','uart']:
            label=str(a['instance'])+', RXD '+a['rx']+', TXD '+a['tx']
            if a.get('stb'):label+=', STB '+a['stb']
            if a.get('rts'):label+=', RTS '+a['rts']
        else:label=item_label(item)
        labels.append(label)
    return {physical[module]:labels}

def source_comments(source):
    # Optional source import only. Runtime generation consumes these explicit
    # JSON comments rather than reading the original BSP again.
    from generator.c_parser import split
    result={}
    for d in declarations(source):
        if not d['array'] or 'cfg' not in d['name']:continue
        labels=[]
        for part in split(source[d['start']+1:d['end']-1]):
            body=part[part.find('{'):] if '{' in part else ''
            match=re.search(r'///<?[ \t]*([^\n\r]+)',body)
            labels.append(match[1].strip() if match else '')
        if any(labels):result[d['name']]=labels
    return result

def checklist(config,target,effective,parameters):
    lines=['# '+config['project']['model']+' · '+config['project']['revision']+' · '+target.upper()+' 引脚与功能检查清单','','由本次 JSON 生成；状态留空供实际硬件验证，不能代表已通过测试。','','| 模块 | 功能名称 | 枚举 / 配置对象 | 引脚 | 总线 / 备注 | 状态 |','| --- | --- | --- | --- | --- | --- |']
    def row(module,name,enum,pins,note=''):
        cells=[module,name,enum,' / '.join(dict.fromkeys(pins)),note,'']
        lines.append('| '+' | '.join(str(c).replace('|','\\|').replace('\n',' ') for c in cells)+' |')
    for id in sorted(effective):
        if not id.startswith('brd.'):continue
        module=id[4:];items=[i for i in config['board']['modules'].get(module,[]) if target in i.get('targets',list(config['targets']))]
        if items:
            for item in items:
                a=item['params'];pins=[v for k,v in a.items() if isinstance(v,str) and re.fullmatch(r'P[A-Z]\d+',v)]
                bus=next((b for b in config['board']['buses'] if b['id']==a.get('bus')),None)
                if bus:pins+=list(bus['pins'].values())
                row(module,item['name'],item['enum'],pins,' / '.join(str(a[k]) for k in ['channel','driver','bus','net','power_supply'] if a.get(k)))
            continue
        candidates=[(path,data) for path,data in parameters.items() if '/cfg/brd_'+module+'_cfg' in path and (not path.startswith('ac78428_boot/') or target=='boot')]
        # Prefer a target-specific configuration over its shared App counterpart.
        if target=='boot' and any(path.startswith('ac78428_boot/') for path,_ in candidates):candidates=[x for x in candidates if x[0].startswith('ac78428_boot/')]
        for path,data in candidates:
            values=data.get('values',{})
            def follow(value,seen=None):
                seen=set() if seen is None else seen;found=pins_in(value)
                if isinstance(value,dict):
                    if '$resource' in value:
                        bus=next((b for b in config['board']['buses'] if b['id']==value['$resource']['id']),None)
                        if bus:found+=list(bus['pins'].values())
                    else:
                        for entry in value.values():found+=follow(entry,seen)
                elif isinstance(value,list):
                    for entry in value:found+=follow(entry,seen)
                elif isinstance(value,str):
                    for name,index in re.findall(r'&([A-Za-z_]\w*)(?:\[(\d+)\])?',value):
                        ref=(name,index)
                        if name in values and ref not in seen:
                            seen.add(ref);obj=values[name]
                            if index and isinstance(obj,list):
                                if int(index)>=len(obj):continue  # Runtime buffers have no pin initializer.
                                obj=obj[int(index)]
                            found+=follow(obj,seen)
                return list(dict.fromkeys(found))
            definitions=next((v.get('definitions',[]) for p,v in parameters.items() if '/def/brd_'+module+'_def.h' in p),[])
            records=[(name,entry) for name,value in values.items() if isinstance(value,list) for entry in value if isinstance(entry,dict) and 'id' in entry]
            if records:
                for n,(name,entry) in enumerate(records):
                    enum=str(entry['id']);definition=next((d for d in definitions if d['enum']==enum),definitions[n] if n<len(definitions) else {})
                    row(module,definition.get('name',enum),enum,follow(entry),name)
            else:
                for name,value in values.items():
                    pins=follow(value)
                    if pins:row(module,name,name,pins,Path(path).name)
    for bus in config['board']['buses']:
        if target in bus.get('targets',list(config['targets'])):row('公共资源',bus['id'],bus['kind']+str(bus['instance']),list(bus['pins'].values()),', '.join(role+'='+pin for role,pin in bus['pins'].items()))
    return '\n'.join(lines)+'\n'
