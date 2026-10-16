"""Reviewed high-level device forms; all instance counts and wiring come from JSON."""
from pathlib import Path
import re
from collections import Counter
from generator.c_format import initializer,identifier,port,scalar
from generator.template import render_file
from generator.modules import compact
from generator.modules.builtins import pinmux

SUPPORTED={'pwr_ctrl','bat_chg','can_trx','crypto','flash'}
TEMPLATES=Path(__file__).resolve().parents[2]/'templates/ac78428'
FAMILY={'pwr_ctrl':'PwrCtrl','bat_chg':'BatChg','can_trx':'CanTrx','crypto':'Crypto','flash':'Flash'}

def declaration(kind,name,value):
    return 'static '+kind+' '+name+' =\n'+initializer(value)+';\n'

def gpio(pin,reverse=False,optional=False):
    if not pin:
        if not optional:raise ValueError('请选择引脚')
        return {'group':'kDrvPortGroupMax','pin':'kDrvPortPin0','reverse':bool(reverse)}
    group,bit=port(pin);return {'group':group,'pin':bit,'reverse':bool(reverse)}

def callback(name,reference,powers):
    code=''
    if reference:
        item=next((i for i in powers if i['enum']==reference),None)
        if item is None:raise ValueError('引用电源不存在：'+reference)
        call='Brd_PwrCtrlSetBaseOn' if item['params'].get('power_kind')=='base' else 'Brd_PwrCtrlSetEnable'
        code='static void '+identifier(name)+'(Bool enable)\n{\n    '+call+'('+identifier(reference)+', enable);\n}\n'
    return (name if reference else 'NULL'),code

def bus_object(module,stem,bus,resources,event,platform,cs=''):
    family=FAMILY[module];kind=bus['kind'];selected=[b for b in resources if b['kind']==kind]
    slot=next(n for n,b in enumerate(selected) if b['id']==bus['id']);objects=[]
    if kind=='spi':
        objects.append('/// SPI'+str(bus['instance'])+', CS '+cs+'\nstatic TDrvSpiPort '+stem+'_port;\n')
        row=gpio(cs);row.pop('reverse');row['index']=bus['instance']
        signal='SPI'+str(bus['instance'])+'_CS0';options=[f for p in platform['pins'] if p['pin']==cs for f in p['functions'] if f['signal'].startswith('SPI'+str(bus['instance'])+'_CS')]
        if not options:raise ValueError(cs+' 不支持 '+signal+' 片选复用')
        row['index']=int(options[0]['signal'].rsplit('CS',1)[1]);row['mux']=options[0]['mux'].replace('ALT','kDrvPortMuxAlt')
        objects.append(declaration('const TDrvSpiCsCfg',stem+'_port_cfg',row));base={'bus_drv':'&'+stem+'_port','bus_drv_cfg':'&'+stem+'_port_cfg'}
    elif kind=='iic':
        objects.append('static TDrvIicDev '+stem+'_port;\n');base={'bus_drv':'&'+stem+'_port'}
    else:raise ValueError(module+'：当前器件适配尚不支持模拟 IIC，请选择物理总线')
    base.update(bus_drv_parent='&g_drv_'+kind+'['+str(slot)+']',bus_drv_parent_cfg='&g_drv_'+kind+'_cfgs['+str(slot)+']')
    suffix='PhySpi' if kind=='spi' else 'PhyIic'
    objects.append(declaration('Brd_T'+family+'Bus'+suffix,stem,{'base':base,'event':event}))
    return '\n'.join(objects),'kBrd_'+family+'Bus'+suffix

def pwr_ctrl(items,powers):
    objects=[];configs={'base':[],'output':[]};entries={'base':[],'output':[]}
    for n,item in enumerate(items):
        a=item['params'];kind=a.get('power_kind','output');mode=a.get('control_mode','gpio')
        if kind not in configs:raise ValueError('Unknown power kind: '+kind)
        reference=a.get('control_ref','') if mode=='power' else a.get('upstream_ref','')
        if mode=='power' and not reference:raise ValueError(item['name']+'：请选择引用电源')
        cb,code=callback('Brd_PwrCtrlPower'+str(n),reference,powers);objects.append(code)
        row={'DoEnable':cb,**gpio(a.get('pin','') if mode=='gpio' else '',a.get('reverse'),optional=mode=='power')}
        slot=len(configs[kind]);configs[kind].append(row)
        array='g_brd_pwr_ctrl_base_cfgs_' if kind=='base' else 'g_brd_pwr_ctrl_cfgs_'
        entries[kind].append({'id':item['enum'],'cfg':'&'+array+'['+str(slot)+']',('ref' if kind=='base' else 'enabled'):0 if kind=='base' else False})
    for kind in ['output','base']:
        if not configs[kind]:continue
        name='g_brd_pwr_ctrl_base_cfgs_' if kind=='base' else 'g_brd_pwr_ctrl_cfgs_'
        objects.append('static const Brd_TPwrCtrlCfg '+name+'[] =\n'+compact.array(name,configs[kind])+';\n')
        name='g_brd_pwr_ctrl_base_' if kind=='base' else 'g_brd_pwr_ctrl_items_'
        objects.append('static '+('Brd_TPwrCtrlBase' if kind=='base' else 'Brd_TPwrCtrlItem')+' '+name+'[] =\n'+compact.array(name,entries[kind])+';\n')
    attr={'count':len(entries['output']),'item':'g_brd_pwr_ctrl_items_' if entries['output'] else 'NULL','base_count':len(entries['base']),'base':'g_brd_pwr_ctrl_base_' if entries['base'] else 'NULL'}
    objects.append('Brd_TPwrCtrlAttr g_brd_pwr_ctrl_attr =\n'+initializer(attr)+';\n')
    return render_file(TEMPLATES/'power.cfg.c.template',{'OBJECTS':'\n'.join(objects)})

def bat_chg(items,powers):
    objects=[];configs=[];entries=[]
    for n,item in enumerate(items):
        a=item['params'];start=len(configs)
        for signal,pin,reverse,reference in [('enable','enable_pin','enable_reverse',a.get('control_ref','') if a.get('enable_mode')=='power' else ''),('done','done_pin','done_reverse',a.get('done_power_ref','')),('charging','charging_pin','charging_reverse',a.get('charging_power_ref',''))]:
            use_pin='' if signal=='enable' and a.get('enable_mode')=='power' else a.get(pin,'')
            if signal=='enable' and not use_pin and not reference:raise ValueError('充电使能引脚或电源引用未配置')
            cb,code=callback('Brd_BatChgPower'+str(n)+'_'+signal,reference,powers);objects.append(code)
            configs.append({'DoEnable':cb,**gpio(use_pin,a.get(reverse),optional=True)})
        entries.append({'id':n,'out':'&g_brd_bat_chg_cfg_['+str(start)+']','in':'&g_brd_bat_chg_cfg_['+str(start+1)+']','incharge':'&g_brd_bat_chg_cfg_['+str(start+2)+']','enabled':False})
    objects.append(declaration('const Brd_TBatChgCfg','g_brd_bat_chg_cfg_[]',configs));objects.append(declaration('Brd_TBatChgItem','g_brd_bat_chg_items_[]',entries))
    objects.append(declaration('Brd_TBatChgAttr','g_brd_bat_chg_attr',{'count':len(items),'item':'g_brd_bat_chg_items_'}).replace('static Brd_TBatChgAttr','Brd_TBatChgAttr'))
    return objects,[]

def external(module,items,powers,buses,platform):
    objects=['extern TDrvSpi g_drv_spi[];\nextern TDrvSpiCfg g_drv_spi_cfgs[];'];entries=[];defines=set();family=FAMILY[module]
    totals=Counter(i['params']['driver'] for i in items);seen=Counter()
    if module=='crypto' and totals['ciu98b']>1:raise ValueError('当前 CIU98B 驱动回调使用全局对象，仅支持一个实例')
    objects.append('static Brd_TEvent g_brd_'+module+'_event_['+str(len(items))+'];')
    for n,item in enumerate(items):
        a=item['params'];driver=a['driver'];chip=driver+('_'+str(seen[driver]) if totals[driver]>1 else '');seen[driver]+=1
        stem='g_brd_'+module+'_'+chip;event='&g_brd_'+module+'_event_['+str(n)+']';bus_enum='kBrd_'+family+'BusNull';bus_ref='NULL'
        if module=='crypto' and driver=='csec':
            objects.append(declaration('Brd_TCryptoDevInChip',stem+'_dev',{'base':{'dev_drv':'&g_drv_csec'},'event':event}));dev='kBrd_CryptoDevInChip';defines.add('BRD_CRYPTO_DEV_CSEC')
        else:
            if (module,driver) not in [('crypto','ciu98b'),('can_trx','tja1445')]:raise ValueError(module+'：当前平台未审核器件 '+driver)
            bus=next((b for b in buses if b['id']==a.get('bus')),None)
            if not bus or bus['kind']!='spi':raise ValueError(item['name']+'：请选择物理 SPI 总线')
            code,bus_enum=bus_object(module,stem+'_bus',bus,buses,event,platform,a.get('cs',''));objects.append(code);bus_ref='&'+stem+'_bus'
            defines.add('BRD_'+module.upper()+'_BUS_PHY_SPI');defines.add('BRD_'+module.upper()+'_DEV_'+driver.upper())
            if module=='crypto':
                objects.append('extern TPerHsmCiu98b g_per_hsm_ciu98b;');cfg={'base':{'dev_drv':'&g_per_hsm_ciu98b'}}
                cb,code=callback('Brd_CryptoPower'+str(n),a.get('power_ref',''),powers);objects.append(code);cfg['DoEnable']=cb
                for key,member in [('reset_pin','rst'),('wakeup_pin','wakeup')]:
                    if not a.get(key):raise ValueError(item['name']+'：请配置 '+key)
                    objects.append('/// '+('复位' if member=='rst' else '唤醒')+', '+a[key]+'\n'+declaration('const Brd_TCryptoGpioCfg',stem+'_'+member,gpio(a[key],a.get(member+'_reverse',True))));cfg[member]='&'+stem+'_'+member
                dev='kBrd_CryptoDevCiu98b';objects.append(declaration('Brd_TCryptoDevCiu98b',stem+'_dev',cfg))
            else:
                if a.get('interrupt_pin'):raise ValueError('当前 TJA1445 板级接口未提供独立中断配置')
                objects.append('static TPerCanTrxTja1445 '+stem+'_per;\nstatic Brd_TCanTrxLocalErrorInfo '+stem+'_errors;')
                objects.append(declaration('const Brd_TCanTrxPinCfg',stem+'_wakeup',gpio(a.get('wakeup_pin',''),a.get('wakeup_reverse',True),optional=True)))
                cfg={'base':{'dev_drv':'&'+stem+'_per','error_info':'&'+stem+'_errors'},'wakeup_pin_cfg':'&'+stem+'_wakeup'}
                dev='kBrd_CanTrxDevTja1445';objects.append(declaration('Brd_TCanTrxDevTja1445',stem+'_dev',cfg))
        entry={'id':item['enum'],'dev':dev,'dev_cfg':'&'+stem+'_dev','bus':bus_enum,'bus_cfg':bus_ref}
        if module=='crypto':entry['is_open']=False
        entries.append(entry)
    objects.append(declaration('Brd_T'+family+'Item','g_brd_'+module+'_items_[]',entries))
    objects.append('Brd_T'+family+'Attr g_brd_'+module+'_attr =\n'+initializer({'count':len(items),'item':'g_brd_'+module+'_items_'})+';\n')
    return objects,defines
def number(value):
    text=re.sub(r'[uUlL]+$','',str(value));return int(text,0) if text.lower().startswith('0x') else int(text)

def flash(items,powers,buses,platform):
    objects=['extern TDrvIic g_drv_iic[];\nextern TDrvIicCfg g_drv_iic_cfgs[];\nextern TDrvSpi g_drv_spi[];\nextern TDrvSpiCfg g_drv_spi_cfgs[];'];entries=[];defines=set();seen=Counter();totals=Counter(i['params']['driver'] for i in items)
    mutex_keys=['internal_flash' if i['params']['driver'] in ['internal','fee'] else 'device_'+str(n) for n,i in enumerate(items)]
    slots={key:n for n,key in enumerate(dict.fromkeys(mutex_keys))}
    objects+=['static Brd_TMutex g_brd_flash_mutex_['+str(len(slots))+'];','static Int32 g_brd_flash_mutex_cnt_['+str(len(slots))+'];','static Brd_TEvent g_brd_flash_event_['+str(len(items))+'];']
    if totals['fee']>1:raise ValueError('当前 Fee 实现使用全局状态，只支持一个实例')
    for n,item in enumerate(items):
        a=item['params'];driver=a['driver'];chip=driver+('_'+str(seen[driver]) if totals[driver]>1 else '');seen[driver]+=1
        if driver=='mx25':raise ValueError('MX25 当前尚未接入工程成员与头文件适配，不能仅生成配置后视为支持')
        stem='g_brd_flash_'+chip;event='&g_brd_flash_event_['+str(n)+']';base={'mutex':'&g_brd_flash_mutex_['+str(slots[mutex_keys[n]])+']','mutex_cnt':'&g_brd_flash_mutex_cnt_['+str(slots[mutex_keys[n]])+']'};bus_enum='kBrd_FlashBusNull';bus_ref='NULL';size=number(a.get('size') or 0);info=[0]
        if driver=='internal':
            base['dev_drv']='&g_drv_flash';dev='kBrd_FlashDevChipPflash';kind='Brd_TFlashDevChipPflash';cfg={'base':base,'flag':'0x01'};defines.add('BRD_FLASH_DEV_CHIP_PFLASH')
            if size<=0 or size%8192:raise ValueError('内部 Flash 容量必须是 8192 字节的正整数倍')
            info={'block_count':1,'sectors_per_block':size//8192,'pages_per_sector':1024,'page_size':8}
        elif driver=='fee':
            fee={key:a[field] for key,field in [('eep_size','size'),('eep_ram_base_addr','eep_ram_base_addr'),('eep_flash_base_addr','eep_flash_base_addr'),('flash_pagesize','flash_page_size'),('flash_min_program_byte','min_program_bytes')]}
            if any(number(v)<=0 for v in fee.values()):raise ValueError('Fee 地址、容量和编程粒度必须配置为正数')
            fee['retry']='3U';objects.append('static TPerFee '+stem+'_per;');objects.append(declaration('TPerFeeCfg',stem+'_cfg',fee));objects.append('static UInt8 '+stem+'_ram['+str(size)+'] __attribute__((at('+str(number(a['eep_ram_base_addr']))+')));')
            base.update(dev_drv='&'+stem+'_per',dev_drv_cfg='&'+stem+'_cfg');dev='kBrd_FlashDevChipEep';kind='Brd_TFlashDevChipEep';cfg={'base':base};defines.update(['BRD_FLASH_DEV_CHIP_EEP','BRD_FLASH_BUS_ON_CHIP_FLASH'])
            objects.append(declaration('Brd_TFlashBusOnChipFlash',stem+'_bus',{'base':{'bus_drv':'&g_drv_flash'},'flag':'0x01'}));bus_enum='kBrd_FlashBusOnChipFlash';bus_ref='&'+stem+'_bus';info={'block_count':8,'sectors_per_block':size//8,'pages_per_sector':1,'page_size':1}
        elif driver in ['at24','xtsdg01gws1g','mx25']:
            bus=next((b for b in buses if b['id']==a.get('bus')),None);expected='iic' if driver=='at24' else 'spi'
            if not bus or bus['kind']!=expected:raise ValueError(item['name']+'：请选择物理 '+expected+' 总线')
            code,bus_enum=bus_object('flash',stem+'_bus',bus,buses,event,platform,a.get('cs',''));objects.append(code);bus_ref='&'+stem+'_bus';defines.add('BRD_FLASH_BUS_PHY_'+expected.upper())
            per_type={'at24':'TPerFramAt24','xtsdg01gws1g':'TPerMmcSpiSd','mx25':'TPerFlashMx25'}[driver];objects.append('static '+per_type+' '+stem+'_per;');base['dev_drv']='&'+stem+'_per';cfg={'base':base}
            if driver=='at24':
                if size not in (4096,16384):raise ValueError('当前 AT24 板级适配支持 4KB 或 16KB，请核对具体芯片')
                suffix='Bl24c32f' if size==4096 else 'Bl24c128f';dev='kBrd_FlashDev'+suffix;kind='Brd_TFlashDevEeprom';cfg['dev_addr']=a.get('address') or 'kPerFramAt24c32DevAddr';defines.add('BRD_FLASH_DEV_'+suffix.upper());info={'block_count':size//512,'sectors_per_block':512,'pages_per_sector':1,'page_size':1}
            elif driver=='xtsdg01gws1g':
                dev='kBrd_FlashDevSdNand';kind='Brd_TFlashDevSdNand';defines.add('BRD_FLASH_DEV_SD_NAND');cfg.update(power_pin='NULL',DoEnable='NULL')
                if a.get('power_pin'):
                    objects.append('/// 电源使能, '+a['power_pin']+'\n'+declaration('const Brd_TFlashPin',stem+'_power',gpio(a['power_pin'],a.get('power_reverse'))));cfg['power_pin']='&'+stem+'_power';cfg['DoEnable']='Brd_FlashPower'+str(n)
                    objects.append('static void '+cfg['DoEnable']+'(Bool enable)\n{\n    TDrvGpioSetLevel(&g_drv_gpio, '+port(a['power_pin'])[0]+', '+port(a['power_pin'])[1]+', enable != '+scalar(bool(a.get('power_reverse')))+');\n}\n')
            else:
                if size<=0 or size%65536:raise ValueError('MX25 容量必须是 65536 字节的正整数倍')
                dev='kBrd_FlashDevMx25';kind='Brd_TFlashDevMx25';defines.add('BRD_FLASH_DEV_MX25');cb,code=callback('Brd_FlashPower'+str(n),a.get('power_ref',''),powers);objects.append(code);cfg['DoEnable']=cb;info={'block_count':size//65536,'sectors_per_block':16,'pages_per_sector':16,'page_size':256}
        else:raise ValueError('Flash 器件尚未审核生成适配：'+driver)
        objects.append(declaration(kind,stem+'_dev',cfg));entries.append({'id':item['enum'],'dev':dev,'dev_cfg':'&'+stem+'_dev','bus':bus_enum,'bus_cfg':bus_ref,'info':info,'is_open':False,'default_offset':a.get('offset') or 0})
    objects.append(declaration('Brd_TFlashItem','g_brd_flash_items_[]',entries));objects.append('Brd_TFlashAttr g_brd_flash_attr =\n'+initializer({'count':len(items),'item':'g_brd_flash_items_'})+';\n')
    return objects,defines

def generate(module,items,config,target,platform):
    powers=[i for i in config['board']['modules'].get('pwr_ctrl',[]) if target in i.get('targets',list(config['targets']))]
    buses=[b for b in config['board']['buses'] if target in b.get('targets',list(config['targets']))]
    if module=='pwr_ctrl':
        by_id={i['enum']:i for i in powers}
        def check(reference,path):
            if reference in path:raise ValueError('电源引用存在循环：'+' → '.join(path+[reference]))
            item=by_id.get(reference)
            if not item:raise ValueError('引用电源不存在：'+reference)
            a=item['params'];next_id=a.get('control_ref') if a.get('control_mode')=='power' else a.get('upstream_ref')
            if next_id:check(next_id,path+[reference])
        for item in items:check(item['enum'],[])
        return pwr_ctrl(items,powers)
    if module=='bat_chg':objects,defines=bat_chg(items,powers)
    elif module=='flash':objects,defines=flash(items,powers,buses,platform)
    else:objects,defines=external(module,items,powers,buses,platform)
    return render_file(TEMPLATES/'devices.cfg.c.template',{'DEFINES':'\n'.join('#define '+d for d in sorted(defines)),'OBJECTS':'\n'.join(objects)})
