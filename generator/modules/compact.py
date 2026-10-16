"""Compact array records; C macro bodies remain in the formal templates."""
import re
from generator.c_format import initializer,scalar

# (member path, shorthand prefix, default for an omitted zero-initialized member).
PORT_GROUP='kDrvPortGroup'; PORT_PIN='kDrvPortPin'
def field(path,prefix='',default=0):return (path,prefix,default)
def pointer(path,array,cast=''):return field(path,cast+'&'+array+'[')
SPECS={
 'g_drv_adc_cfgs_':('INIT_ANALOG_ADC_CFG',[field('index')]),
 'g_drv_adc_ch_cfgs_':('INIT_ANALOG_CHANNEL_CFG',[field('group',PORT_GROUP),field('pin',PORT_PIN),field('mux'),field('x'),field('y'),field('offset'),field('ref_vol'),field('spt'),field('index')]),
 'g_brd_analog_dev_in_chips_':('INIT_ANALOG_DEV_IN_CHIP',[pointer('base.dev_drv','g_drv_adc_chs_'),pointer('base.dev_drv_cfg','g_drv_adc_ch_cfgs_'),pointer('dev_drv_parent','g_drv_adcs_'),pointer('dev_drv_parent_cfg','g_drv_adc_cfgs_')]),
 'g_brd_analog_items_':('INIT_ANALOG_ITEM',[field('id'),field('dev'),pointer('dev_cfg','g_brd_analog_dev_in_chips_','(void*)'),field('bus'),field('bus_cfg',default='NULL')]),
 'g_brd_pwr_ctrl_cfgs_':('INIT_PWR_CTRL_CFG',[field('DoEnable',default='NULL'),field('group',PORT_GROUP),field('pin',PORT_PIN,'kDrvPortPin0'),field('reverse',default=False)]),
 'g_brd_pwr_ctrl_base_cfgs_':('INIT_PWR_CTRL_CFG',[field('DoEnable',default='NULL'),field('group',PORT_GROUP),field('pin',PORT_PIN,'kDrvPortPin0'),field('reverse',default=False)]),
 'g_brd_pwr_ctrl_items_':('INIT_PWR_CTRL_ITEM',[field('id'),pointer('cfg','g_brd_pwr_ctrl_cfgs_'),field('enabled',default=False)]),
 'g_brd_pwr_ctrl_base_':('INIT_PWR_CTRL_BASE',[field('id'),pointer('cfg','g_brd_pwr_ctrl_base_cfgs_'),field('ref')]),
 'g_brd_misc_ctrl_cfgs_':('INIT_MISC_CTRL_CFG',[field('group',PORT_GROUP),field('pin',PORT_PIN),field('flag'),field('reverse',default=False)]),
 'g_brd_misc_ctrl_items_':('INIT_MISC_CTRL_ITEM',[field('id'),pointer('cfg','g_brd_misc_ctrl_cfgs_'),field('enabled',default=False)]),
 'g_drv_uart_cfgs_':('INIT_UART_CFG',[field('index'),field('rx_group',PORT_GROUP),field('rx_pin',PORT_PIN),field('rx_pin_mux'),field('tx_group',PORT_GROUP),field('tx_pin',PORT_PIN),field('tx_pin_mux'),field('rts_group',PORT_GROUP),field('rts_pin',PORT_PIN,'kDrvPortPin0'),field('mode'),field('dma_en',default=False),field('dma_ch_rx'),field('dma_ch_tx'),field('dma_src_rx'),field('dma_src_tx')]),
 'g_brd_uart_dev_in_chip_':('INIT_UART_DEV_IN_CHIP',[pointer('base.dev_drv','g_drv_uart_'),pointer('base.dev_drv_cfg','g_drv_uart_cfgs_')]),
 'g_brd_uart_items_':('INIT_UART_ITEM',[field('id'),field('dev'),pointer('dev_cfg','g_brd_uart_dev_in_chip_'),field('bus'),field('bus_cfg',default='NULL')]),
}

def flatten(value,prefix=''):
    result={}
    for key,entry in value.items():
        name=prefix+key
        if isinstance(entry,dict):result.update(flatten(entry,name+'.'))
        else:result[name]=entry
    return result

def array(name,value):
    if name not in SPECS:return initializer(value)
    macro,fields=SPECS[name];rows=[]
    for row in value:
        # Keep extensions intact until their macro signature has been reviewed.
        if not isinstance(row,dict) or '$ifdef' in row:
            rows.append(row);continue
        flat=flatten(row)
        if set(flat)-{f[0] for f in fields}:
            rows.append(row);continue
        args=[]
        for path,prefix,default in fields:
            arg=scalar(flat.get(path,default))
            if prefix:
                if prefix.endswith('['):
                    match=re.fullmatch(re.escape(prefix)+r'(\d+)\]',arg)
                    if not match:break
                    arg=match[1]
                elif arg.startswith(prefix):arg=arg[len(prefix):]
                else:break
            args.append(arg)
        else:
            rows.append(macro+'('+', '.join(args)+')');continue
        rows.append(row)
    return initializer(rows)
