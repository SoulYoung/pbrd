"""Reviewed adapters from additional board references; counts always come from JSON."""
from pathlib import Path
import re
from generator.c_format import initializer,port,identifier,scalar
from generator.template import render_file
from generator.modules.builtins import pinmux
TEMPLATES=Path(__file__).resolve().parents[2]/'templates/ac78428'
SUPPORTED={'meter','ic_card','bat_chg_mgr','ext_rtc','xcu_spi'}
FAMILIES={'meter':'Meter','ic_card':'IcCard','bat_chg_mgr':'BatChgMgr'}

def callback(module,index,supply):
    name='Brd_'+FAMILIES[module]+'Power'+str(index)
    code=''
    if supply:
        identifier(supply)
        code='/// 前置电源：'+supply+'\nstatic void '+name+'(Bool enable)\n{\n    Brd_PwrCtrlSetBaseOn('+supply+', enable);\n}\n'
    return name if supply else 'NULL',code

def meter(items,platform):
    parents=sorted({int(i['params']['instance']) for i in items});slots={n:i for i,n in enumerate(parents)}
    channels=[];devices=[];entries=[];callbacks=[];used=set()
    for n,item in enumerate(items):
        a=item['params'];instance=int(a['instance']);channel=int(a['channel']);key=(instance,channel)
        if key in used:raise ValueError(item['name']+': duplicate PSMU capture channel')
        used.add(key);group,pin=port(a['pin']);mux=pinmux(platform,a['pin'],'PWM'+str(instance)+'_CH'+str(channel))
        channels.append({'group':group,'pin':pin,'mux':mux,'index':channel,'wide':a['wide']})
        enable,code=callback('meter',n,a.get('power_supply',''));callbacks.append(code)
        devices.append({'base':{'dev_drv':'&g_drv_psmu_ch_['+str(n)+']','dev_drv_cfg':'&g_drv_psmu_ch_cfg_['+str(n)+']'},'dev_drv_parent':'&g_drv_psmu_['+str(slots[instance])+']','dev_drv_parent_cfg':'&g_drv_psmu_cfg_['+str(slots[instance])+']','DoEnable':enable})
        entries.append({'id':item['enum'],'dev':'kBrd_MeterDevInChipPulse','dev_cfg':'&g_brd_meter_dev_in_chip_pulse_['+str(n)+']','bus':'kBrd_MeterBusNull','bus_cfg':'NULL','is_open':False})
    return render_file(TEMPLATES/'meter.cfg.c.template',{'PARENT_COUNT':len(parents),'COUNT':len(items),'PARENTS':initializer([{'index':n} for n in parents]),'CHANNELS':initializer(channels),'CALLBACKS':'\n'.join(callbacks),'DEVICES':initializer(devices),'ITEMS':initializer(entries)})

def ic_card_drivers(params):
    supported=['sle4428','sle4442','at24']
    explicit=any('support_'+driver in params for driver in supported)
    if explicit:
        if any(not isinstance(params.get('support_'+driver,False),bool) for driver in supported):raise ValueError('IC card support flags must be boolean')
        selected=[driver for driver in supported if params.get('support_'+driver,False)]
    else:
        legacy={'sle4418':'sle4428','sle4432':'sle4442'}.get(params.get('driver'),params.get('driver','auto'))
        if legacy not in supported+['auto']:raise ValueError('Unsupported IC card implementation: '+str(legacy))
        selected=supported if legacy=='auto' else [legacy]
    if not selected:raise ValueError('IC card: select at least one supported card type')
    return selected

def ic_card(items,platform):
    objects=[];entries=[]
    families={'sle4428':('TPerIcCardSle4428','kBrd_IcCardCatSle4428'),'sle4442':('TPerIcCardSle4442','kBrd_IcCardCatSle4442'),'at24':('TPerFramAt24','kBrd_IcCardCatAt24')}
    for n,item in enumerate(items):
        a=item['params'];selected=ic_card_drivers(a)
        if a.get('bus'):raise ValueError(item['name']+': this card adapter uses private GPIO SCL/SDA, not a public physical IIC bus')
        pins={}
        for member,key,reverse in [('pwr','power_pin','power_reverse'),('rst','reset_pin','reset_reverse'),('chk','detect_pin','detect_reverse'),('scl','clock_pin',None),('sda','io_pin',None)]:
            group,pin=port(a[key]);pins[member]={'group':group,'pin':pin,'reverse':bool(a.get(reverse,False)) if reverse else False}
        enable,code=callback('ic_card',n,a.get('power_supply',''));objects.append(code)
        objects.append('/// '+item['name']+'：电源、复位、插卡检测、时钟、数据\nstatic const Brd_TIcCardPins g_brd_ic_card_pins_'+str(n)+' =\n'+initializer(pins)+';\n')
        last='NULL'
        for driver in selected:
            type,category=families[driver];symbol='g_brd_ic_card_'+str(n)+'_'+driver
            objects.append('static '+type+' '+symbol+'_drv;')
            value={'next':last,'dev':category,'dev_drv':'&'+symbol+'_drv','scl':'NULL','sda':'NULL','rst':'NULL'}
            if driver=='at24':
                objects.append('static TIdpEnumIic '+symbol+'_iic;')
                address=a.get('address') or 'kPerFramAt24DevAddr'
                if a.get('address') and not 0<=int(str(address),0)<=255:raise ValueError(item['name']+': AT24 address must be 0..255')
                value.update(bus_drv='&'+symbol+'_iic',dev_addr=address)
            objects.append('static Brd_TIcCardDevItem '+symbol+'_dev =\n'+initializer(value)+';\n');last='&'+symbol+'_dev'
        entries.append({'id':item['enum'],'receiver':'NULL','OnExist':'NULL','DoEnable':enable,'dev_item':last,'pins':'&g_brd_ic_card_pins_'+str(n),'state':0,'is_open':False,'pwr_enable':False})
    return render_file(TEMPLATES/'ic_card.cfg.c.template',{'OBJECTS':'\n'.join(objects),'ITEMS':initializer(entries)})

def bat_chg_mgr(items,platform):
    configs=[];entries=[]
    for item in items:
        a=item['params'];refs={}
        for role,key in [('out','enable_pin'),('in','done_pin'),('incharge','charging_pin')]:
            if not a.get(key):
                if role!='incharge':raise ValueError(item['name']+': enable/done pins are required')
                refs[role]='NULL';continue
            group,pin=port(a[key]);refs[role]='&g_brd_bat_chg_mgr_cfg_['+str(len(configs))+']'
            configs.append({'DoEnable':'NULL','group':group,'pin':pin,'reverse':a.get(key.replace('_pin','_reverse'),False)})
        entries.append({'id':item['enum'],**refs,'enabled':a['initial'],'is_open':False})
    return render_file(TEMPLATES/'bat_chg_mgr.cfg.c.template',{'CONFIGS':initializer(configs),'ITEMS':initializer(entries)})

def generate(module,items,platform,buses=None):return ext_rtc(items,platform,buses) if module=='ext_rtc' else globals()[module](items,platform)

def ext_rtc(items,platform,buses):
    objects=[];entries=[];devices=set();used=set()
    supported={'bm8563':('Bm8563','Brd_TExtRtcDevBm8563','kBrdExtRtcDevBm8563','kBm8563ChipAddr',0x51),'rx8010sj':('Rx8010sj','Brd_TExtRtcDevBaseRx8010sj','kBrdExtRtcDevBaseRx8010sj','kRx8010sjChipAddr',0x32)}
    for n,item in enumerate(items):
        a=item['params'];driver=a['driver']
        if driver not in supported:raise ValueError(item['name']+': reviewed RTC implementations are BM8563 / RX8010SJ')
        if a['bus'] not in buses:raise ValueError(item['name']+': RTC requires configured physical IIC')
        if a.get('interrupt_pin'):raise ValueError(item['name']+': configure the RTC interrupt GPIO in brd.ext_int and reference its enum')
        family,type,enum,address,default=supported[driver];number=int(str(a['address']),0) if a.get('address') else default
        if not 0<=number<=0x7F:raise ValueError(item['name']+': RTC address must be 7-bit')
        key=(a['bus'],number)
        if key in used:raise ValueError(item['name']+': duplicate RTC address on '+a['bus'])
        used.add(key);devices.add(driver)
        extra=''
        if driver=='rx8010sj':
            clock=a.get('timer_clock','kRx8010sjClksrc1Hz');output=a.get('timer_output','kRx8010sjOutPinIrq1')
            if clock not in ['kRx8010sjClksrc4096Hz','kRx8010sjClksrc64Hz','kRx8010sjClksrc1Hz','kRx8010sjClksrcMin','kRx8010sjClksrcHour'] or output not in ['kRx8010sjOutPinIrq1','kRx8010sjOutPinIrq2']:raise ValueError(item['name']+': invalid RX8010SJ timer configuration')
            extra='static TPerRtcRx8010sjTimerConfig g_brd_ext_rtc_'+str(n)+'_timer = { .irq_pin = '+output+', .clk_src = '+clock+' };\n'
        value={'base':{'dev_drv':'&g_brd_ext_rtc_'+str(n)+'_per','mutex':'&g_brd_ext_rtc_mutex_['+str(n)+']','dev_addr':a.get('address') or address}}
        if driver=='rx8010sj':value['pin_cfg']='&g_brd_ext_rtc_'+str(n)+'_timer'
        objects.append(render_file(TEMPLATES/'ext_rtc.instance.c.template',{'NAME':item['name'],'INDEX':n,'FAMILY':family,'DEVICE_TYPE':type,'DEVICE_CONFIG':initializer(value),'PARENT':buses[a['bus']],'TIMER':extra}))
        entries.append({'id':item['enum'],'dev':enum,'dev_cfg':'&g_brd_ext_rtc_'+str(n)+'_dev','bus':'kBrdExtRtcBusPhyIic','bus_cfg':'&g_brd_ext_rtc_'+str(n)+'_bus','is_open':False})
    return render_file(TEMPLATES/'ext_rtc.cfg.c.template',{'DEVICE_DEFINES':'\n'.join('#define BRD_EXT_RTC_DEV_'+d.upper() for d in sorted(devices)),'COUNT':len(items),'OBJECTS':'\n'.join(objects),'ITEMS':initializer(entries)})

def xcu_spi(items,platform):
    configs=[];devices=[];entries=[];objects=[];used=set()
    for n,item in enumerate(items):
        a=item['params'];instance=int(a['instance'])
        if instance in used:raise ValueError(item['name']+': duplicate XCU SPI hardware instance')
        used.add(instance);row={}
        for key,role in [('clk','SCK'),('sout','SOUT'),('sin','SIN'),('cs','CS'+str(a['cs_index']))]:
            group,pin=port(a[key]);row[key+'_group']=group;row[key+'_pin']=pin;row[key+'_mux']=pinmux(platform,a[key],'SPI'+str(instance)+'_'+role)
        group,pin=port(a['req']);row.update(req_group=group,req_pin=pin,req_mux='kDrvPortMuxGpio',req_level=a['req_level'],cs_index=int(a['cs_index']),index=instance,dma_ch_rx=int(a['dma_rx']),dma_ch_tx=int(a['dma_tx']),dma_src_rx='DMA_REQ_SPI'+str(instance)+'_RX',dma_src_tx='DMA_REQ_SPI'+str(instance)+'_TX',cpol=int(a['cpol']),cpha=int(a['cpha']),frame_size=int(a['frame_size']))
        if row['cpol'] not in [0,1] or row['cpha'] not in [0,1] or not 1<=row['frame_size']<=32 or int(a['timeout_ms'])<0:raise ValueError(item['name']+': invalid XCU SPI mode/frame/timeout')
        configs.append(row);function='Brd_XcuSpiAfterOpen'+str(n)
        objects.append('/// 打开后恢复 REQ 非请求电平\nstatic void '+function+'(void)\n{\n    const TDrvXcuSpiCfg *cfg = &g_drv_xcu_spi_cfgs_['+str(n)+'];\n    TDrvGpioSetLevel(&g_drv_gpio, cfg->req_group, cfg->req_pin, '+scalar(a['req_reverse'])+');\n}\n')
        devices.append({'base':{'dev_drv':'&g_drv_xcu_spi_['+str(n)+']','dev_drv_cfg':'&g_drv_xcu_spi_cfgs_['+str(n)+']'},'DoAfterOpen':function,'req_reverse':a['req_reverse'],'timeout_ms':int(a['timeout_ms'])})
        entries.append({'id':item['enum'],'dev':'kBrd_XcuSpiDevInChip','dev_cfg':'&g_brd_xcu_spi_dev_in_chip_['+str(n)+']','bus':'kBrd_XcuSpiBusNull','bus_cfg':'NULL','is_open':False})
    return render_file(TEMPLATES/'xcu_spi.cfg.c.template',{'COUNT':len(items),'CONFIGS':initializer(configs),'CALLBACKS':'\n'.join(objects),'DEVICES':initializer(devices),'ITEMS':initializer(entries)})
