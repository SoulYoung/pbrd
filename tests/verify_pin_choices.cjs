/* Verify pin input rendering and candidate validation without browser dependencies. */
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync(require('path').join(__dirname,'../ui/app.js'),'utf8');
const sandbox={};vm.createContext(sandbox);
const helpers=source.slice(source.indexOf('function opts('),source.indexOf('const out='));
const validity=source.slice(source.indexOf('function validPin('),source.indexOf('async function save('));
vm.runInContext("const E=x=>String(x??'').replace(/&/g,'&amp;').replace(/\"/g,'&quot;').replace(/</g,'&lt;');"+helpers+validity+'this.draw=input;this.validate=validPin;',sandbox);
const html=sandbox.draw('GPIO','data-param="pin"','PB9','pin',[['PB9','PB9 · 脚 1'],['PB10','PB10 · 脚 2']]);
assert(html.includes('data-pin-choice'));assert(html.includes('<datalist'));assert(html.includes('<option value="PB9">'));assert(!html.includes('<select'));
const second=sandbox.draw('SDA','data-pin="SDA"','','pin',['PB10']);assert.notEqual(/list="([^"]+)"/.exec(html)[1],/list="([^"]+)"/.exec(second)[1]);
function field(value,options){return {value,list:{options:options.map(value=>({value}))},setCustomValidity(message){this.message=message;}};}
let b=field(' pb9 ',['PB9','PB10']);assert(sandbox.validate(b));assert.equal(b.value,'PB9');assert.equal(b.message,'');
b=field('PZ99',['PB9','PB10']);assert(!sandbox.validate(b));assert(b.message);
b=field('PA1',['PB9','PB10']);assert(!sandbox.validate(b)); // Existing MCU pin with incompatible signal.
b=field('',['PB9']);assert(sandbox.validate(b)); // Optional pin remains clearable.
b=field('pb10',['PB10']);assert(sandbox.validate(b));b.value='PZ99';assert(!sandbox.validate(b));b.value='PB10';assert(sandbox.validate(b));assert.equal(b.message,'');
assert(source.includes("if(['gpio','adc','signal'].includes(type))type='pin'"));
assert(source.includes("b.pins[r]||'','pin'"));assert(source.includes('if(invalid){invalid.reportValidity();return;}'));
console.log('PASS editable pin choices, unique lists, case normalization, allowed-candidate validation, optional empty values and save guard');
