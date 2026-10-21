/* Frontend migration. Preserve legacy parameters and require review of unresolved mappings. */
(()=>{'use strict';
const copy=x=>JSON.parse(JSON.stringify(x)),isObject=x=>x&&typeof x==='object'&&!Array.isArray(x);
function visible(field,params){
 if(field.visible_if&&!params[field.visible_if])return false;
 return Object.entries(field.visible_when||{}).every(([key,wanted])=>Array.isArray(wanted)?wanted.includes(params[key]):params[key]===wanted);
}
function gpio(row){
 if(!isObject(row))return '';
 const group=/^kDrvPortGroup([A-Z])$/.exec(row.group||row.port||'');
 const pin=/^(?:kDrvPortPin)?(\d+)$/.exec(String(row.pin??''));
 return group&&pin?'P'+group[1]+pin[1]:'';
}
function migrate(input,specs,catalog){
 if(!isObject(input)||input.format!=='pbrd-project'||input.schema_version!==1)throw Error('需要 pbrd-project / schema_version=1 的项目 JSON');
 const x=copy(input);
 if(!isObject(x.project)||!isObject(x.platform)||!isObject(x.build)||!isObject(x.targets)||!isObject(x.board)||!isObject(x.board.modules)||!Array.isArray(x.board.buses))throw Error('项目 JSON 缺少必要结构');
 if(!x.project.revision)x.project.revision=(x.project.hardware_revision||'')+(x.project.software_revision||'');
 for(const key of ['model','revision','author','date'])if(typeof x.project[key]!=='string')throw Error('项目字段无效：'+key);
 x.project.author=x.project.author.trim()||'软件工程院';
 const targets=Object.keys(x.targets);
 if(!targets.length||targets.some(t=>!['app','boot'].includes(t)))throw Error('目标只能是 App / Boot');
 for(const t of Object.values(x.targets))for(const key of ['requested','disabled','touched']){
  if(!Array.isArray(t[key])||t[key].some(v=>typeof v!=='string'||!/^(brd|drv|per|hal|idp)\.[a-z0-9_.]+$/.test(v)))throw Error('模块状态无效：'+key);
  t[key]=[...new Set(t[key].flatMap(id=>id==='brd.csec'?['drv.csec']:['brd.flash_mgr_inner','brd.iic_mgr_inner'].includes(id)?[]:[id]))];
 }
 const params=x.codegen?.parameters||{},legacy=(x.ui_schema_version||1)<2;
 const values=k=>params['ac78428/cfg/brd_'+k+'_cfg.c']?.values||{};
 const definition=k=>params['ac78428/def/brd_'+k+'_def.h']?.definitions||[];
 const deref=(v,reference)=>{const m=/&(\w+)(?:\[(\d+)\])?/.exec(reference||'');return m?(m[2]!==undefined?v[m[1]]?.[Number(m[2])]:v[m[1]])||{}:{};};
 const busId=bus=>bus?.base?.bus_drv_parent?.$resource?.id||'';
 function add(k,index,id,data,note=''){
  const entry=catalog.find(e=>e.enum===id)||definition(k).find(e=>e.enum===id)||{};
  (x.board.modules[k]??=[]).push({uid:'legacy_'+k+'_'+index,name:entry.name||id,enum:id,base_enum:entry.base_enum||'',enum_override:false,params:data,targets:targets.slice(),...(note?{review_note:note}:{})});
 }
 for(const [key,list] of Object.entries(x.board.modules)){
  if(!Array.isArray(list))throw Error('模块实例数组无效：'+key);
  const ids=new Set();
  for(const item of list){
   if(!isObject(item)||typeof item.uid!=='string'||ids.has(item.uid)||typeof item.name!=='string'||typeof item.enum!=='string'||!isObject(item.params))throw Error('模块实例无效：'+key);
   ids.add(item.uid);
   if(item.targets&&(!Array.isArray(item.targets)||item.targets.some(t=>!['app','boot'].includes(t))))throw Error('实例目标无效：'+key);
  }
 }
 if(legacy){
  const supply=callback=>x.metadata?.import_callback_references?.[callback]||x.metadata?.power_callback_references?.[callback]||'';
  if(!x.board.modules.ic_card?.length){
   const v=values('ic_card');
   (v.g_brd_ic_card_item_||[]).forEach((row,n)=>{
    const raw=deref(v,row.pins),keys=['pwr','rst','chk','scl','sda'],pins=Array.isArray(raw)?Object.fromEntries(keys.map((k,n)=>[k,raw[n]])):raw;
    const data={power_pin:gpio(pins.pwr),power_reverse:!!pins.pwr?.reverse,reset_pin:gpio(pins.rst),reset_reverse:!!pins.rst?.reverse,detect_pin:gpio(pins.chk),detect_reverse:!!pins.chk?.reverse,clock_pin:gpio(pins.scl),io_pin:gpio(pins.sda),power_supply:supply(row.DoEnable),support_at24:false,support_sle4428:false,support_sle4442:false,address:''};
    let ref=row.dev_item;const seen=new Set();
    while(ref&&ref!=='NULL'){
     if(seen.has(ref))throw Error('IC 卡识别链循环：'+ref);seen.add(ref);
     const dev=deref(v,ref),type=String(dev.dev||'').toLowerCase(),driver=['at24','sle4428','sle4442'].find(k=>type.endsWith(k));
     if(!driver)throw Error('IC 卡导入遇到未知卡型：'+dev.dev);
     data['support_'+driver]=true;
     if(driver==='at24')data.address=dev.dev_addr==='kPerFramAt24DevAddr'?'0xA0':String(dev.dev_addr??'');
     ref=dev.next;
    }
    add('ic_card',n,String(row.id),data,row.DoEnable&&row.DoEnable!=='NULL'&&!data.power_supply?'无法解析 IC 卡前置电源回调：'+row.DoEnable:'');
    x.board.modules.ic_card[x.board.modules.ic_card.length-1].targets=targets.filter(t=>x.targets[t].requested.includes('brd.ic_card'));
   });
  }
  if(!x.board.modules.meter?.length){
   const v=values('meter');
   (v.g_brd_meter_items_||[]).forEach((row,n)=>{
    const dev=deref(v,row.dev_cfg),cfg=deref(v,dev.base?.dev_drv_cfg),parent=deref(v,dev.dev_drv_parent_cfg),power_supply=supply(dev.DoEnable);
    add('meter',n,String(row.id),{pin:gpio(cfg),instance:Number(parent.index),channel:Number(cfg.index),wide:!!cfg.wide,power_supply},dev.DoEnable&&dev.DoEnable!=='NULL'&&!power_supply?'无法解析计量前置电源回调：'+dev.DoEnable:'');
    x.board.modules.meter[x.board.modules.meter.length-1].targets=targets.filter(t=>x.targets[t].requested.includes('brd.meter'));
   });
  }
  if(!x.board.modules.ext_rtc?.length){
   const v=values('ext_rtc');
   (v.g_brd_ext_rtc_item_||[]).forEach((row,n)=>{
    const kind=String(row.dev||'').toLowerCase(),driver=kind.includes('rx8010sj')?'rx8010sj':kind.includes('bm8563')?'bm8563':'';
    if(!driver)throw Error('外部 RTC 导入遇到未知器件：'+row.dev);
    const dev=deref(v,row.dev_cfg),bus=deref(v,row.bus_cfg),timer=deref(v,dev.pin_cfg),raw=dev.base?.dev_addr;
    const known={kRx8010sjChipAddr:'0x32',kBm8563ChipAddr:'0x51'},address=known[raw]??raw??'';
    const enumeration=typeof row.id==='string'&&/^kBrd_/.test(row.id)?row.id:'kBrd_ExtRtcId'+(driver==='rx8010sj'?'Rx8010sj':'Bm8563')+(n?'_'+n:'');
    add('ext_rtc',n,enumeration,{driver,bus:busId(bus),address:String(address),timer_clock:timer.clk_src||'kRx8010sjClksrc1Hz',timer_output:timer.irq_pin||'kRx8010sjOutPinIrq1',timer_custom:!!dev.pin_cfg&&dev.pin_cfg!=='NULL'});
    const item=x.board.modules.ext_rtc[x.board.modules.ext_rtc.length-1];item.name=driver.toUpperCase()+' 外部 RTC';item.targets=targets.filter(t=>x.targets[t].requested.includes('brd.ext_rtc'));
   });
  }
  if(!x.board.modules.pwr_ctrl?.length){
   const v=values('pwr_ctrl');let n=0;
   for(const [array,kind] of [['g_brd_pwr_ctrl_base_','base'],['g_brd_pwr_ctrl_items_','output']])for(const row of v[array]||[]){
    const cfg=deref(v,row.cfg),pin=gpio(cfg),hasCallback=cfg.DoEnable&&cfg.DoEnable!=='NULL';
    add('pwr_ctrl',n++,String(row.id),{power_kind:kind,control_mode:pin?'gpio':'power',pin,reverse:!!cfg.reverse,control_ref:'',upstream_ref:''},hasCallback?'旧配置含电源回调 '+cfg.DoEnable+'，请确认前置或引用电源。':'');
   }
  }
  if(!x.board.modules.bat_chg?.length){
   const v=values('bat_chg');
   (v.g_brd_bat_chg_items_||[]).forEach((row,n)=>{const out=deref(v,row.out),done=deref(v,row.in),status=deref(v,row.incharge);add('bat_chg',n,'kBrd_BatChgId'+n,{enable_mode:gpio(out)?'gpio':'power',enable_pin:gpio(out),enable_reverse:!!out.reverse,control_ref:'',done_pin:gpio(done),done_reverse:!!done.reverse,charging_pin:gpio(status),charging_reverse:!!status.reverse},out.DoEnable&&out.DoEnable!=='NULL'?'原使能回调 '+out.DoEnable+' 已保留在旧参数中，请选择对应电源。':'');});
  }
  for(const k of ['can_trx','crypto','flash'])if(!x.board.modules[k]?.length){
   const v=values(k),rows=v['g_brd_'+k+'_items_']||[];
   rows.forEach((raw,n)=>{
    const row=raw.$ifdef?raw.value:raw,dev=deref(v,row.dev_cfg),bus=deref(v,row.bus_cfg),port=deref(v,bus.base?.bus_drv_cfg),kind=String(row.dev||'').toLowerCase();
    let driver='';
    if(k==='crypto')driver=kind.includes('inchip')?'csec':kind.includes('ciu98m25')?'ciu98m25':'ciu98b';
    if(k==='can_trx')driver=kind.includes('sit1145')?'sit1145':'tja1445';
    if(k==='flash')driver=kind.includes('chippflash')?'internal':kind.includes('chipeep')?'fee':kind.includes('sdnand')?'xtsdg01gws1g':kind.includes('bl24')?'at24':kind.includes('gd5')?'gd5f':'mx25';
    const data={driver,bus:busId(bus),cs:gpio(port)};
    if(k==='can_trx')data.wakeup_pin=gpio(deref(v,dev.wakeup_pin_cfg));
    if(k==='crypto'){data.reset_pin=gpio(deref(v,dev.rst));data.wakeup_pin=gpio(deref(v,dev.wakeup));}
    if(k==='flash'){
     const fee=v.g_per_fee_cfg||{};data.power_pin=gpio(deref(v,dev.power_pin));data.address=dev.dev_addr||'';data.offset=row.default_offset||0;
     const info=row.info;data.size=isObject(info)?Object.values(info).reduce((a,b)=>a*(Number(b)||0),1):0;
     if(driver==='fee')Object.assign(data,{size:fee.eep_size,eep_ram_base_addr:fee.eep_ram_base_addr,eep_flash_base_addr:fee.eep_flash_base_addr,flash_page_size:fee.flash_pagesize,min_program_bytes:fee.flash_min_program_byte});
    }
    add(k,n,String(row.id),data);
   });
  }
 }
 // App XCU is a singleton, not an enum-indexed device array.
 if(!x.board.modules.xcu?.length&&x.targets.app?.requested.includes('brd.xcu')){
  const cfg=values('xcu').g_drv_xcu_spi_cfg;
  if(cfg){
   const n=v=>Number(String(v).replace(/[uUlL]+$/,'')),pin=key=>gpio({group:cfg[key+'_group'],pin:cfg[key+'_pin']});
   const data={instance:n(cfg.index),clk:pin('clk'),sout:pin('sout'),sin:pin('sin'),cs:pin('cs'),req:pin('req'),cs_index:n(cfg.cs_index),req_level:cfg.req_level,cpol:String(cfg.cpol),cpha:String(cfg.cpha),frame_size:n(cfg.frame_size),dma_rx:n(cfg.dma_ch_rx),dma_tx:n(cfg.dma_ch_tx),stack_size:512};
   add('xcu',0,'kBrd_XcuId0',data,'请核对 XCU 线程栈大小；旧结构化参数未记录未初始化的栈数组大小。');
   const item=x.board.modules.xcu[0];item.name='App XCU 通信';item.targets=['app'];
  }
 }
 for(const [k,spec] of Object.entries(specs)){
  const list=x.board.modules[k]??=[];
  for(const item of list){
   const a=item.params;
   if(k==='ic_card'){
    const old={sle4418:'sle4428',sle4432:'sle4442'}[a.driver]||a.driver,types=['at24','sle4428','sle4442'],explicit=types.some(c=>('support_'+c) in a);
    for(const type of types)if(!(('support_'+type) in a))a['support_'+type]=explicit?false:!old||old==='auto'||old===type;
    if('driver' in a){a.legacy_driver??=a.driver;delete a.driver;}
   }
   if(k==='flash'&&!('section_write' in a)){
    const v=values('flash'),raw=(v.g_brd_flash_items_||[]).find(row=>(row.$ifdef?row.value:row).id===item.enum),row=raw?.$ifdef?raw.value:raw;
    const source=row?deref(v,a.driver==='internal'?row.dev_cfg:row.bus_cfg):{};
    a.section_write=['internal','fee'].includes(a.driver)&&!!(Number(String(source.flag||0).replace(/[uUlL]+$/,''))&1);
   }
   if(k==='ext_rtc'&&!('timer_custom' in a))a.timer_custom=a.driver==='rx8010sj'&&((a.timer_clock&&a.timer_clock!=='kRx8010sjClksrc1Hz')||(a.timer_output&&a.timer_output!=='kRx8010sjOutPinIrq1'));
   if(k==='can'&&!('fd_enabled' in a))a.fd_enabled=!!a.fd_enum;
   for(const field of spec.fields||[]){
    if(!(field.key in a))a[field.key]=copy(field.value);
    if(field.type==='num'&&typeof a[field.key]==='string'&&/^(?:0x[0-9a-f]+|[0-9]+)[uUlL]+$/i.test(a[field.key]))a[field.key]=Number(a[field.key].replace(/[uUlL]+$/,''));
    if(field.type==='num'&&!['number','string'].includes(typeof a[field.key]))throw Error('数值参数无效：'+k+'.'+field.key);
    if(field.type==='bool'&&typeof a[field.key]!=='boolean')throw Error('布尔参数无效：'+k+'.'+field.key);
    if(!['bool','num'].includes(field.type)&&!['string','number'].includes(typeof a[field.key]))throw Error('配置参数无效：'+k+'.'+field.key);
   }
  }
 }
 const buses=new Set();
 for(const b of x.board.buses){
  if(!isObject(b)||typeof b.id!=='string'||!/^\w+$/.test(b.id)||buses.has(b.id)||!['iic','spi','soft_iic'].includes(b.kind)||!Number.isInteger(b.instance)||b.instance<0||!isObject(b.pins)||!isObject(b.mux))throw Error('公共总线配置无效');
  if(b.targets&&(!Array.isArray(b.targets)||b.targets.some(t=>!['app','boot'].includes(t))))throw Error('公共总线目标无效');
  if((b.frequency_hz!==undefined&&!Number.isFinite(Number(b.frequency_hz)))||Object.values(b.pins).some(v=>typeof v!=='string')||Object.values(b.mux).some(v=>typeof v!=='string'))throw Error('公共总线引脚或频率无效');
  buses.add(b.id);
 }
 x.output??={directory:'',automatic:true,mode:'create'};x.driver_settings??={};
 if(!isObject(x.output)||typeof x.output.directory!=='string'||typeof x.output.automatic!=='boolean'||!isObject(x.driver_settings))throw Error('输出或驱动配置结构无效');
 x.output.json_directory??='';if(typeof x.output.json_directory!=='string')throw Error('JSON 保存位置无效');
 x.output.json_filename??='';if(typeof x.output.json_filename!=='string')throw Error('JSON 文件名无效');
 x.ui_schema_version=2;
 return x;
}
window.PBRD_MODEL={visible,migrate,gpio};
})();
