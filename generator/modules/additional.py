"""Reviewed adapters from additional board references; counts always come from JSON."""
from pathlib import Path
import re
from collections import Counter
from generator.c_format import initializer,port,identifier,scalar,address_expression
from generator.template import render_file
from generator.modules.builtins import pinmux
TEMPLATES=Path(__file__).resolve().parents[2]/'templates/ac78428'
SUPPORTED={'meter','ic_card','bat_chg_mgr','ext_rtc','xcu_spi','xcu'}
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
    return render_file(TEMPLATES/'meter.cfg.c.template',{'PARENT_COUNT':len(parents),'COUNT':len(items),'PARENTS':initializer([{'index':n} for n in parents]),'CHANNELS':initializer(channels),'CALLBACKS':'\n'.join(callbacks),'DEVICES':initializer(devices).replace('.req_reverse = True,','.req_reverse = True,    ///< REQ 非请求电平为高').replace('.req_reverse = False,','.req_reverse = False,    ///< REQ 非请求电平为低').replace('.timeout_ms  = ','.timeout_ms  = '),'ITEMS':initializer(entries)})

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
        a=item['params'];selected=ic_card_drivers(a);slot='' if len(items)==1 else '_slot'+str(n)
        address,define=address_expression(a.get('address'),'kPerFramAt24DevAddr',0xA0,'BRD_IC_CARD'+slot.upper()+'_AT24_ADDRESS',8)
        if define:objects.append(define)
        if a.get('bus'):raise ValueError(item['name']+': this card adapter uses private GPIO SCL/SDA, not a public physical IIC bus')
        pins={}
        for member,key,reverse in [('pwr','power_pin','power_reverse'),('rst','reset_pin','reset_reverse'),('chk','detect_pin','detect_reverse'),('scl','clock_pin',None),('sda','io_pin',None)]:
            group,pin=port(a[key]);pins[member]={'group':group,'pin':pin,'reverse':bool(a.get(reverse,False)) if reverse else False}
        enable,code=callback('ic_card','Slot'+str(n) if len(items)>1 else '',a.get('power_supply',''));objects.append(code)
        text=initializer(pins)
        labels={'pwr':'pwr, '+a['power_pin']+', IC卡电源控制引脚','rst':'rst, '+a['reset_pin']+', IC卡复位引脚','chk':'identify, '+a['detect_pin']+', IC卡在线检测引脚, '+('低' if a.get('detect_reverse') else '高')+'电平有效','scl':'scl, '+a['clock_pin']+', IC卡时钟引脚','sda':'sda, '+a['io_pin']+', IC卡数据引脚'}
        for member,label in labels.items():
            text=re.sub(r'(\.'+member+r'\s*=\s*\{)\n',lambda m:m[1]+'\n        /// '+label+'\n',text,count=1)
        for member in ['scl','sda']:
            pattern=r'(\.'+member+r'\s*=\s*\{.*?\.reverse\s*=\s*False,)'
            text=re.sub(pattern,lambda m:m[1]+' ///< 直接引用端口函数, 不起作用',text,count=1,flags=re.S)
        if len(items)>1:objects.append('/// '+item['name'])
        objects.append('static const Brd_TIcCardPins g_brd_ic_card_pins'+slot+'_ =\n'+text+';\n')
        last='NULL'
        for driver in selected:
            type,category=families[driver];symbol='g_brd_ic_card_'+driver+slot
            objects.append('/// '+driver.upper()+'~'*(76-len(driver)))
            objects.append('static '+type+' '+symbol+'_drv_;')
            value={'next':last,'dev':category,'dev_drv':'&'+symbol+'_drv_','scl':'NULL','sda':'NULL','rst':'NULL'}
            if driver=='at24':
                objects.append('static TIdpEnumIic '+symbol+'_iic_;')
                # Address is normalized to the chip macro or a named project override.
                value.update(bus_drv='&'+symbol+'_iic_',dev_addr=address)
            objects.append('static Brd_TIcCardDevItem '+symbol+'_dev_ =\n'+initializer(value)+';\n');last='&'+symbol+'_dev_'
        objects.append('/// '+'~'*76+'\n')
        entries.append({'id':item['enum'],'receiver':'NULL','OnExist':'NULL','DoEnable':enable,'dev_item':last,'pins':'&g_brd_ic_card_pins'+slot+'_','state':0,'is_open':False,'pwr_enable':False})
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
    objects=[];entries=[];devices=set();used=set();totals=Counter(i['params']['driver'] for i in items);instances=Counter()
    supported={'bm8563':('Bm8563','Brd_TExtRtcDevBm8563','kBrdExtRtcDevBm8563','kBm8563ChipAddr',0x51),'rx8010sj':('Rx8010sj','Brd_TExtRtcDevBaseRx8010sj','kBrdExtRtcDevBaseRx8010sj','kRx8010sjChipAddr',0x32)}
    for n,item in enumerate(items):
        a=item['params'];driver=a['driver']
        if driver not in supported:raise ValueError(item['name']+': reviewed RTC implementations are BM8563 / RX8010SJ')
        if a['bus'] not in buses:raise ValueError(item['name']+': RTC requires configured physical IIC')
        if a.get('interrupt_pin'):raise ValueError(item['name']+': configure the RTC interrupt GPIO in brd.ext_int and reference its enum')
        family,type,enum,address,default=supported[driver]
        chip=driver+('_'+str(instances[driver]) if totals[driver]>1 else '');instances[driver]+=1
        expression,define=address_expression(a.get('address'),address,default,'BRD_EXT_RTC_'+chip.upper()+'_ADDRESS')
        number=int(re.sub(r'[uUlL]+$','',str(a['address'])),0) if a.get('address') and a['address']!=address else default
        if define:objects.append(define)
        if not 0<=number<=0x7F:raise ValueError(item['name']+': RTC address must be 7-bit')
        key=(a['bus'],number)
        if key in used:raise ValueError(item['name']+': duplicate RTC address on '+a['bus'])
        used.add(key);devices.add(driver)
        extra=''
        custom=driver=='rx8010sj' and a.get('timer_custom',False)
        if custom:
            clock=a.get('timer_clock','kRx8010sjClksrc1Hz');output=a.get('timer_output','kRx8010sjOutPinIrq1')
            if clock not in ['kRx8010sjClksrc4096Hz','kRx8010sjClksrc64Hz','kRx8010sjClksrc1Hz','kRx8010sjClksrcMin','kRx8010sjClksrcHour'] or output not in ['kRx8010sjOutPinIrq1','kRx8010sjOutPinIrq2']:raise ValueError(item['name']+': invalid RX8010SJ timer configuration')
            extra='static TPerRtcRx8010sjTimerConfig g_brd_ext_rtc_'+chip+'_timer_ = { .irq_pin = '+output+', .clk_src = '+clock+' };\n'
        value={'base':{'dev_drv':'&g_brd_ext_rtc_'+chip+'_','mutex':'&g_brd_ext_rtc_mutex_['+str(n)+']','dev_addr':expression}}
        if custom:value['pin_cfg']='&g_brd_ext_rtc_'+chip+'_timer_'
        objects.append(render_file(TEMPLATES/'ext_rtc.instance.c.template',{'NAME':item['name'],'INDEX':n,'CHIP':chip,'FAMILY':family,'DEVICE_TYPE':type,'DEVICE_CONFIG':initializer(value),'PARENT':buses[a['bus']],'TIMER':extra}))
        entries.append({'id':n,'dev':enum,'dev_cfg':'&g_brd_ext_rtc_dev_'+chip+'_','bus':'kBrdExtRtcBusPhyIic','bus_cfg':'&g_brd_ext_rtc_bus_phy_iic_'+chip+'_','is_open':False})
    return render_file(TEMPLATES/'ext_rtc.cfg.c.template',{'DEVICE_DEFINES':'\n'.join('#define BRD_EXT_RTC_DEV_'+d.upper() for d in sorted(devices)),'COUNT':len(items),'OBJECTS':'\n'.join(objects),'ITEMS':initializer(entries)})

def xcu_spi_comments(text,a,instance):
    labels={'clk_group':'CLK '+a['clk']+'，SPI'+str(instance)+' 时钟','sout_group':'SOUT '+a['sout']+'，MCU 发送','sin_group':'SIN '+a['sin']+'，MCU 接收','cs_group':'CS '+a['cs']+'，硬件片选 '+str(a['cs_index']),'req_group':'REQ '+a['req']+'，主处理器请求信号','req_level':'下升沿有效, False: 同相器, True: 反相器','dma_ch_rx':'接收 DMA 通道','dma_ch_tx':'发送 DMA 通道','dma_src_rx':'SPI'+str(instance)+' 接收请求源','dma_src_tx':'SPI'+str(instance)+' 发送请求源','cpol':'设置SPI的CPOL, TBOX和AIDVR均为0','cpha':'设置SPI的CPAH, TBOX为1,AIDVR为0','frame_size':'设置spi一帧的bit数; TBOX为32,AIDVR为8'}
    for key,label in labels.items():
        text=re.sub(r'(^[ \t]*\.'+key+r'\s*=.*?,)$',lambda m:m[1]+'    ///< '+label,text,count=1,flags=re.M)
    return text


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
        configs.append(xcu_spi_comments(initializer(row,4),a,instance));function='Brd_XcuSpi'+str(instance)+'DoAfterOpen'
        objects.append('/// 打开后恢复 REQ 非请求电平\nstatic void '+function+'(void)\n{\n    const TDrvXcuSpiCfg *cfg = &g_drv_xcu_spi_cfgs_['+str(n)+'];\n    TDrvGpioSetLevel(&g_drv_gpio, cfg->req_group, cfg->req_pin, '+scalar(a['req_reverse'])+');\n}\n')
        devices.append({'base':{'dev_drv':'&g_drv_xcu_spi_['+str(n)+']','dev_drv_cfg':'&g_drv_xcu_spi_cfgs_['+str(n)+']'},'DoAfterOpen':function,'req_reverse':a['req_reverse'],'timeout_ms':int(a['timeout_ms'])})
        entries.append({'id':item['enum'],'dev':'kBrd_XcuSpiDevInChip','dev_cfg':'&g_brd_xcu_spi_dev_in_chip_['+str(n)+']','bus':'kBrd_XcuSpiBusNull','bus_cfg':'NULL','is_open':False})
    device_text=re.sub(r'(^[ \t]*\.timeout_ms\s*=.*?,)$',r'\1    ///< 通信超时，单位 ms',initializer(devices),flags=re.M)
    device_text=re.sub(r'(^[ \t]*\.req_reverse\s*=.*?,)$',r'\1    ///< REQ 非请求电平，True: 高，False: 低',device_text,flags=re.M)
    return render_file(TEMPLATES/'xcu_spi.cfg.c.template',{'COUNT':len(items),'CONFIGS':'{\n'+',\n'.join('    '+row for row in configs)+',\n}','CALLBACKS':'\n'.join(objects),'DEVICES':device_text,'ITEMS':initializer(entries)})


def xcu(items,platform):
    if len(items)!=1:raise ValueError('App XCU requires exactly one instance')
    a=items[0]['params'];instance=int(a['instance']);row={};used=set()
    for key,role in [('clk','SCK'),('sout','SOUT'),('sin','SIN'),('cs','CS'+str(a['cs_index']))]:
        if a[key] in used:raise ValueError('XCU pins must be distinct: '+a[key])
        used.add(a[key]);group,bit=port(a[key]);row[key+'_group']=group;row[key+'_pin']=bit;row[key+'_mux']=pinmux(platform,a[key],'SPI'+str(instance)+'_'+role)
    if a['req'] in used or not any(p['pin']==a['req'] for p in platform['pins']):raise ValueError('Invalid XCU request pin')
    group,bit=port(a['req']);row.update(req_group=group,req_pin=bit,req_mux='kDrvPortMuxGpio',req_level=a['req_level'],cs_index=int(a['cs_index']),index=instance,dma_ch_rx=int(a['dma_rx']),dma_ch_tx=int(a['dma_tx']),dma_src_rx='DMA_REQ_SPI'+str(instance)+'_RX',dma_src_tx='DMA_REQ_SPI'+str(instance)+'_TX',cpol=int(a['cpol']),cpha=int(a['cpha']),frame_size=int(a['frame_size']))
    size=int(a['stack_size'])
    if row['cpol'] not in [0,1] or row['cpha'] not in [0,1] or not 1<=row['frame_size']<=32 or size<=0 or size%8:raise ValueError('Invalid XCU mode, frame size or stack alignment')
    if not 0<=row['dma_ch_rx']<16 or not 0<=row['dma_ch_tx']<16 or row['dma_ch_rx']==row['dma_ch_tx']:raise ValueError('Invalid XCU DMA channels')
    text=initializer(row)
    text=xcu_spi_comments(text,a,instance)
    return render_file(TEMPLATES/'xcu.cfg.c.template',{'SPI_CONFIG':text,'STACK_SIZE':size})
