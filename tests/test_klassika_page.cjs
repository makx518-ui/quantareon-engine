const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const html=fs.readFileSync(process.argv[2]||path.join(__dirname,'../../site-release/razbor-ru.html'),'utf8');
let count=0;
for(const m of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)){new vm.Script(m[1]);count++;}
assert.match(html,/id="kConfirmPlace"/);
const nodes={kConfirmPlace:{checked:true}},ctx={window:{QUANTAREON_ASTRO_DANNYE:{}},
 $:id=>nodes[id],панель:{hidden:false},сводка:{hidden:true},телоСводки:{innerHTML:''},кнОплата:{classList:{add(){}}}};
const functions=['э','коорд','показатьСводку'];
for(const name of functions){const start=html.indexOf('  function '+name+'(');assert.ok(start>=0);const end=html.indexOf('\n  }',start);new vm.Script(html.slice(start,end+4)).runInNewContext(ctx);}
const data={тип:'натал',дата:'09.11.1981',время:'03:15',место:'Москва, Россия',пол:'M',_shirota:55.75204,_dolgota:37.61781,_gmt:3};
ctx.показатьСводку(data);assert.equal(data._подтверждено,false);assert.equal(nodes.kConfirmPlace.checked,false);
assert.match(ctx.телоСводки.innerHTML,/55\.75204/);assert.match(ctx.телоСводки.innerHTML,/GMT\+3/);
ctx.показатьСводку({...data,время:null});assert.match(ctx.телоСводки.innerHTML,/без домов и ASC/);
assert.match(html,/_подтверждено!==true/);assert.match(html,/if\(версия!==поколение\)return/);
console.log(`Site: ${count} inline scripts parse; confirmation, coordinates, historical GMT, unknown time and stale-response checks pass`);
