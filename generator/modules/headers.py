"""Shared definition-header template context. Platform extras stay in templates."""
from pathlib import Path
import re
from generator.template import render_file

def header(module,items,project=None):
    from generator.c_format import macro
    project=project or {};family={'analog':'Analog','axis':'Axis','led':'Led','can':'Can','canfd':'Canfd','ext_int':'ExtInt','switch':'Switch','misc_ctrl':'MiscCtrl','uart':'Uart','meter':'Meter','ic_card':'IcCard','bat_chg_mgr':'BatChgMgr','ext_rtc':'ExtRtc','xcu_spi':'XcuSpi','pwr_ctrl':'PwrCtrl','flash':'Flash','crypto':'Crypto','can_trx':'CanTrx'}[module]
    rows=[('kBrd_'+family+'IdBase','0','基础值')]
    for index,item in enumerate(items):
        expression='BRD_DEF_BASE_ID('+item['base_enum']+', '+str(index)+')' if item.get('base_enum') else 'kBrd_'+family+'IdBase + '+str(index)
        rows.append((item['enum'],expression,item['name']))
    width=max(len(r[0]) for r in rows)+4
    enum='\n'.join('    '+r[0].ljust(width)+'= '+(r[1]+',').ljust(56)+'///< '+r[2] for r in rows)+'\n    kBrd_'+family+'IdMax,'
    macros='\n'.join('#define '+macro(module,i['enum'],family) for i in items)
    path=Path(__file__).resolve().parents[2]/'templates/common/brd_def.h.template'
    values={'MODULE':module,'FAMILY':family,'GUARD':module.upper(),'DESCRIPTION':{'analog':'模拟量','axis':'轴传感器','led':'LED','can':'CAN','canfd':'CANFD','ext_int':'外部中断','switch':'开关量','misc_ctrl':'杂项控制','uart':'串口','meter':'脉冲计量','ic_card':'IC 卡','bat_chg_mgr':'电池充电管理','ext_rtc':'外部 RTC','xcu_spi':'XCU SPI 接口','pwr_ctrl':'电源控制','flash':'存储器','crypto':'加密器件','can_trx':'CAN 收发器'}[module],'PROJECT':project.get('model',''),'REVISION':project.get('hardware_revision','')+project.get('software_revision',''),'DATE':project.get('date',''),'AUTHOR':project.get('author',''),'ENUM_CONTENT':enum,'DEFINE_CONTENT':macros}
    specific=path.parents[1]/'ac78428/app/def'/('brd_'+module+'_def.h.template')
    if specific.exists():path=specific
    from generator.template import TOKEN
    needed=set(TOKEN.findall(path.read_text(encoding='utf-8-sig')))
    return render_file(path,{k:v for k,v in values.items() if k in needed})
