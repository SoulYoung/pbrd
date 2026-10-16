"""Resolve declared module capabilities and resource dependencies."""
def resolve_modules(config,specs,target,additional=None):
    requested=config['targets'][target]['requested'];disabled=set(config['targets'][target].get('disabled',[]));result=set();visiting=set()
    def visit(id):
        if id in visiting:return
        visiting.add(id)
        if id in disabled:raise ValueError('Required module was manually disabled: '+id)
        result.add(id)
        if id.startswith('brd.'):
            k=id[4:]
            for dep in specs.get(k,{}).get('dependencies',[]):visit(dep)
            if not config['board']['modules'].get(k):
                for dep in (additional or {}).get(id,[]):visit(dep)
            for item in config['board']['modules'].get(k,[]):
                if target not in item.get('targets',list(config['targets'])):continue
                a=item['params'];implementations=specs.get(k,{}).get('implementations',[])
                if k=='ic_card':
                    from generator.modules.additional import ic_card_drivers
                    selected=set(ic_card_drivers(a));matches=[x for x in implementations if x['value'] in selected]
                else:matches=[x for x in implementations if x['value']==a.get('driver')]
                for impl in matches:
                    if impl.get('module'):visit(impl['module'])
                    for dep in impl.get('dependencies',[]):visit(dep)
                if any(a.get(key) for key in ['control_ref','upstream_ref','power_ref','done_power_ref','charging_power_ref']):visit('brd.pwr_ctrl')
                if a.get('bus') and (not matches or any(x.get('bus_kinds') for x in matches)):
                    b=next((b for b in config['board']['buses'] if b['id']==a['bus']),None)
                    if b:
                        visit('idp.iic' if b['kind']=='soft_iic' else 'drv.'+b['kind'])
                        if b['kind']=='soft_iic':visit('drv.gpio')
    for id in requested:
        if id not in disabled:visit(id)
    return result

