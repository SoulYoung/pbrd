"""Reviewed high-level module adapters; templates own file and record layout."""
from pathlib import Path
from collections import Counter
import re
from generator.c_format import initializer,port,scalar,address_expression
from generator.template import render_file
from generator.modules.compact import array
TEMPLATES=Path(__file__).resolve().parents[2]/'templates'
SUPPORTED={'analog','axis','led','ext_int','can','uart','misc_ctrl','switch'}
def analog(items,platform):
    available={(p['pin'],f['signal']) for p in platform['pins'] for f in p['functions'] if re.fullmatch(r'ADC\d+_IN\d+',f['signal'])}
    parents=sorted({int(i['params']['channel'].split('_')[0][3:]) for i in items});slots={n:i for i,n in enumerate(parents)}
    channels=[];devices=[];entries=[]
    for index,item in enumerate(items):
        a=item['params'];channel=a['channel']
        if (a['pin'],channel) not in available:raise ValueError(item['name']+': ADC pin/channel mismatch')
        if float(a['y'])<=0 or float(a['reference_mv'])<=0:raise ValueError(item['name']+': ADC y/reference must be positive')
        group,pin=port(a['pin']);parent=slots[int(channel.split('_')[0][3:])]
        channels.append({'group':group,'pin':pin,'mux':'kDrvPortMuxDefault','x':a['x'],'y':a['y'],'offset':a['offset'],'ref_vol':str(a['reference_mv'])+'U','spt':a['sample_time'],'index':int(channel.split('_IN')[1])})
        devices.append({'base':{'dev_drv':'&g_drv_adc_chs_['+str(index)+']','dev_drv_cfg':'&g_drv_adc_ch_cfgs_['+str(index)+']'},'dev_drv_parent':'&g_drv_adcs_['+str(parent)+']','dev_drv_parent_cfg':'&g_drv_adc_cfgs_['+str(parent)+']'})
        entries.append({'id':item['enum'],'dev':'kBrd_AnalogDevInChip','dev_cfg':'(void*)&g_brd_analog_dev_in_chips_['+str(index)+']','bus':'kBrd_AnalogBusNull','bus_cfg':'NULL'})
    return render_file(TEMPLATES/'ac78428/analog.cfg.c.template',{'ADC_PARENT_COUNT':len(parents),'ADC_CHANNEL_COUNT':len(items),'ADC_PARENT_CONFIGS':array('g_drv_adc_cfgs_',[{'index':n} for n in parents]),'ADC_CHANNEL_CONFIGS':array('g_drv_adc_ch_cfgs_',channels),'DEVICE_CONFIGS':array('g_brd_analog_dev_in_chips_',devices),'ITEM_CONFIGS':array('g_brd_analog_items_',entries)})
def axis(items,buses):
    objects=[];entries=[];files=set();devices=set();used=set()
    totals=Counter(i['params']['driver'] for i in items);instances=Counter()
    supported={'da280b':('Da280b','kPerAxisDa280bChipAddr',0x27),'lsm6dsl':('Lsm6dsl','kPerAxisLsm6dslChipAddr',0x6B)}
    for n,item in enumerate(items):
        a=item['params'];driver=a['driver']
        if driver not in supported:raise ValueError('Axis adapter unavailable: '+driver)
        if a['bus'] not in buses:raise ValueError('Axis requires configured physical IIC: '+a['bus'])
        if any(a.get(k) for k in ['range','rate','interrupt_pin']):raise ValueError(item['name']+': runtime range/rate/interrupt adaptation is not implemented')
        chip=driver+('_'+str(instances[driver]) if totals[driver]>1 else '');instances[driver]+=1
        family,address,default=supported[driver];number=int(str(a['address']),0) if a.get('address') and a['address']!=address else default
        if not 0<=number<=0x7F:raise ValueError(item['name']+': invalid 7-bit IIC address')
        key=(a['bus'],number)
        if key in used:raise ValueError('Duplicate Axis IIC address on '+a['bus'])
        used.add(key);devices.add(driver)
        objects.append(render_file(TEMPLATES/'ac78428/axis.instance.c.template',{'NAME':item['name'],'INDEX':n,'CHIP':chip,'FAMILY':family,'ADDRESS':address if number==default else scalar(a['address']),'PARENT':buses[a['bus']]}))
        entries.append({'id':item['enum'],'dev':'kBrd_AxisDev'+family,'dev_cfg':'&g_brd_axis_dev_'+chip+'_','bus':'kBrd_AxisBusPhyIic','bus_cfg':'&g_brd_axis_bus_phy_iic_dev_'+chip+'_','is_open':False})
        files.add('product/src/per/axis/'+driver+'/per_axis_'+driver+'_ex.c')
    code=render_file(TEMPLATES/'ac78428/axis.cfg.c.template',{'DEVICE_DEFINES':'\n'.join('#define BRD_AXIS_DEV_'+d.upper() for d in sorted(devices)),'COUNT':len(items),'DEVICE_AND_BUS_OBJECTS':'\n'.join(objects),'ITEM_ARRAY':'static Brd_TAxisItem g_brd_axis_items_[] =\n'+initializer(entries)+';\n'})
    return code,sorted(files)
def pinmux(platform,pin,signal):
    mux=next((f['mux'] for p in platform['pins'] if p['pin']==pin for f in p['functions'] if f['signal']==signal),None)
    if mux is None:raise ValueError(pin+' does not support '+signal)
    return mux.replace('ALT','kDrvPortMuxAlt')
def values(module,items,platform):
    result={};configs=[];entries=[];devices=[]
    for n,item in enumerate(items):
        a=item['params'];id=item['enum']
        if module in ['led','ext_int','misc_ctrl','switch']:
            group,pin=port(a['pin'])
            if module=='led':
                configs.append({'port':group,'pin':pin,'reverse':a['reverse']});entries.append({'id':id,'cfg':'&g_brd_led_cfg_['+str(n)+']','is_on':a['initial']})
            elif module=='ext_int':
                triggers={'disabled':'Disable','rising':'Rising','falling':'Falling','both':'EdgeBoth'}
                if a.get('pull','disabled')!='disabled':raise ValueError('EXT_INT pull configuration is not supported by this adapter')
                configs.append({'group':group,'pin':pin,'run_trigger':'kDrvGpioIntTrigger'+triggers[a['run_trigger']],'sleep_trigger':'kDrvGpioIntTrigger'+triggers[a['sleep_trigger']]});entries.append({'id':id,'drv_cfg':'&g_brd_ext_int_cfgs['+str(n)+']','is_open':False})
            elif module=='misc_ctrl':
                configs.append({'group':group,'pin':pin,'flag':a.get('flag',0),'reverse':a['reverse']});entries.append({'id':id,'cfg':'&g_brd_misc_ctrl_cfgs_['+str(n)+']','enabled':a['initial']})
            else:
                configs.append('INIT_SWITCH_DEV_IN_CHIP_CFG('+a['pin'][1]+', '+a['pin'][2:]+', '+{'disabled':'Disabled','up':'Up','down':'Down'}[a.get('pull','disabled')]+', '+scalar(a['reverse'])+')')
                devices.append('INIT_SWITCH_DEV_IN_CHIP('+str(n)+')');entries.append('INIT_SWITCH_DEV_IN_CHIP_ITEM('+str(n)+', kBrd_SwitchDevInChip, '+id+')')
        elif module in ['can','uart']:
            hardware=int(a['instance'][3:] if module=='can' else a['instance'][4:])
            if module=='uart' and not a['rx'] and not a['tx']:raise ValueError(item['name']+': UART requires RX or TX')
            rxg,rxp=port(a['rx']) if a['rx'] or module=='can' else ('kDrvPortGroupMax','kDrvPortPin0')
            txg,txp=port(a['tx']) if a['tx'] or module=='can' else ('kDrvPortGroupMax','kDrvPortPin0')
            row={'rx_group':rxg,'tx_group':txg};role='stb' if module=='can' else 'rts'
            if a.get(role):g,p=port(a[role]);row[role+'_group']=g;row[role+'_pin']=p
            else:row[role+'_group']='kDrvPortGroupMax'
            row.update(rx_pin=rxp,tx_pin=txp,tx_pin_mux=pinmux(platform,a['tx'],a['instance']+'_TX') if a['tx'] else 'kDrvPortMuxDefault',rx_pin_mux=pinmux(platform,a['rx'],a['instance']+'_RX') if a['rx'] else 'kDrvPortMuxDefault')
            if module=='can':
                if a.get('stb_reverse'):raise ValueError('CAN STB reverse has no matching field in the current driver')
                row['id']=id
                row['index']=hardware
                order=['rx_group','tx_group','stb_group','rx_pin','tx_pin','stb_pin','tx_pin_mux','rx_pin_mux','id','index']
                row={key:row[key] for key in order if key in row}
                devices.append({'base':{'dev_drv':'&g_drv_can_['+str(n)+']','dev_drv_cfg':'&g_drv_can_cfgs_['+str(n)+']'},'fd_buf':('&g_brd_canfd_data_['+str(n)+']' if a.get('fd_enabled',bool(a.get('fd_enum'))) else 'NULL')})
                entries.append({'id':id,'dev':'kBrd_CanDevInChip','dev_cfg':'&g_brd_can_dev_in_chip_['+str(n)+']','bus':'kBrd_CanBusNull','bus_cfg':'NULL'})
            else:
                row['index']=hardware
                row.update(mode='kDrvUartMode'+a['mode'],dma_en=a['dma'],dma_ch_rx=int(a['dma_rx']),dma_ch_tx=int(a['dma_tx']),dma_src_rx='DMA_REQ_UART'+str(hardware)+'_RX',dma_src_tx='DMA_REQ_UART'+str(hardware)+'_TX')
                devices.append({'base':{'dev_drv':'&g_drv_uart_['+str(n)+']','dev_drv_cfg':'&g_drv_uart_cfgs_['+str(n)+']'}})
                entries.append({'id':id,'dev':'kBrd_UartDevInChip','dev_cfg':'&g_brd_uart_dev_in_chip_['+str(n)+']','bus':'kBrd_UartBusNull','bus_cfg':'NULL'})
            configs.append(row)
    names={'led':('g_brd_led_cfg_','g_brd_led_items_'),'ext_int':('g_brd_ext_int_cfgs','g_brd_ext_int_items_'),'misc_ctrl':('g_brd_misc_ctrl_cfgs_','g_brd_misc_ctrl_items_'),'switch':('g_brd_switch_cfgs_','g_brd_switch_items_'),'can':('g_drv_can_cfgs_','g_brd_can_items_'),'uart':('g_drv_uart_cfgs_','g_brd_uart_items_')}
    cfg,records=names[module];result[cfg]=configs;result[records]=entries
    if module=='switch':result['g_brd_switch_dev_in_chip_']=devices
    if module=='can':
        result['g_brd_can_dev_in_chip_']=devices;result['g_brd_canfd_items_']=[{**row,'id':item['params'].get('fd_enum') or item['enum'].replace('kBrd_CanId','kBrd_CanfdId')} for row,item in zip(entries,items) if item['params'].get('fd_enabled',bool(item['params'].get('fd_enum')))]
    result['g_brd_'+module+'_attr']={'count':len(items),'item':records}
    if module=='can':result['g_brd_canfd_attr']={'count':len(result['g_brd_canfd_items_']),'item':'g_brd_canfd_items_' if result['g_brd_canfd_items_'] else 'NULL'}
    if module=='uart':result['g_brd_uart_dev_in_chip_']=devices
    return result


def can_power(items,powers):
    groups={}
    for item in items:
        refs=tuple(dict.fromkeys(item['params'].get(key,'') for key in ['power_ref','power_ref_aux'] if item['params'].get(key)))
        for reference in refs:
            if not any(p['enum']==reference and p['params'].get('power_kind')=='base' for p in powers):raise ValueError(item['name']+': CAN public supply not configured: '+reference)
        if refs:groups.setdefault(refs,[]).append(item['enum'])
    lines=[]
    for refs,ids in groups.items():
        lines.append('        if ('+' || '.join('Brd_CanBusNo(handle) == '+identifier for identifier in ids)+')')
        lines.append('        {')
        for reference in refs:lines.append('            Brd_PwrCtrlSetBaseOn('+reference+', enable);')
        lines.append('        }')
    body='\n'.join(lines)
    setup='        Bool enable = (power == kBrd_PowerSupplyOn);' if lines else '        (void)handle;'
    return '\n'.join(['Int32 Brd_CanDoPowerSupply(Brd_THandle handle, Int32 power)','{','    Int32 result = kBrd_ErrorCodeNotSupportLine;','','    if (power == kBrd_PowerSupplyOn || power == kBrd_PowerSupplyOff)','    {',setup,body,'        result = kBrd_ErrorCodeSuccess;','    }','','    return result;','}'])
