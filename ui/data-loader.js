/* Live catalog refresh is transactional; configuration state belongs to app.js. */
(()=>{'use strict';
const seed=window.PBRD_DATA;
const state={mode:location.protocol.startsWith('http')?'live':'offline',enumStatus:'内置资料',pinStatus:'内置资料',sourceSettings:seed.source_settings,platforms:Object.values(seed.platforms).map(x=>({mcu:x.mcu,package:x.package}))};
async function request(path,body){const r=await fetch(path,{cache:'no-store',...(body!==undefined?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})});const x=await r.json();if(!r.ok)throw Error(x.error||'资料读取失败');return x;}
function installSync(data){
 if(data?.platform?.format!=='pbrd-platform'||data.platform.schema_version!==1||!Array.isArray(data.platform.pins)||data.platform.pins.some(p=>typeof p.pin!=='string'||!Array.isArray(p.functions))||!Array.isArray(data.enums?.enum_catalog)||!Array.isArray(data.products?.products)||!Array.isArray(data.module_library?.modules))throw Error('同步资料不完整');
 Object.assign(seed,{enum_catalog:data.enums.enum_catalog,source_hash:data.enums.source_hash,enum_source:data.enums.source,product_catalog:data.products.products,product_source:data.products.source,source_settings:data.settings,module_library:data.module_library,live_sources:data});
 seed.platforms[data.mcu]=data.platform;seed.drivers[data.mcu]=data.drivers;
 state.sourceSettings=data.settings;state.platforms=data.platforms;state.enumStatus='本地头文件';state.pinStatus=data.mcu+' 引脚资料';
 return data;
}
async function sync(mcu){if(state.mode!=='live')throw Error('本地同步需通过 start-config.cmd 打开；当前仍可导入、编辑和保存 JSON。');return installSync(await request('/api/local-sync',{mcu}));}
async function platform(mcu){
 if(state.mode==='live')await sync(mcu);
 if(!seed.platforms[mcu])throw Error('该平台尚未配置引脚 JSON，请在平台资料设置中补充');
 return seed.platforms[mcu];
}
async function saveSettings(settings){if(state.mode!=='live')throw Error('保存平台资料设置需通过 start-config.cmd 打开');const saved=await request('/api/source-settings',settings);state.sourceSettings=saved;return saved;}
window.PBRD_LOADER={state,sync,platform,saveSettings,saveProject:body=>request('/api/save-project-json',body),generateProject:body=>request('/api/generate-project',body),chooseDirectory:initial=>request('/api/select-json-directory',{initial})};
window.PBRD_READY=(async()=>{
 if(state.mode==='live'){try{
  state.context=await request('/api/context');state.sourceSettings=await request('/api/source-settings');
  const mcu=Object.keys(state.sourceSettings.platforms)[0];if(!mcu)throw Error('请配置至少一个平台资料来源');
  await sync(mcu);
 }catch(e){state.error='自动同步失败，保留内置资料：'+e.message;} }
 return seed;
})();
})();
