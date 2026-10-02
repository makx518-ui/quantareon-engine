const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');

async function check(filename) {
  const html = fs.readFileSync(path.join(__dirname, '../frontend', filename), 'utf8');
  let scripts=0;
  for (const script of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)) {
    new vm.Script(script[1], {filename}); scripts++;
  }
  const ids = ['pl','cn','cr','cd','la','lo','tz','dt','tm','ppl','pcn','pcr','pcd','py','px','pz','pd','pt','geo','geoP','st'];
  const nodes = Object.fromEntries(ids.map(id => [id, {
    value:'', dataset:{}, style:{}, innerHTML:'', textContent:'', listeners:{},
    children:[],appendChild(n){this.children.push(n)},addEventListener(event, fn){this.listeners[event]=fn;}
  }]));
  const document = {getElementById: id => nodes[id] || null,createElement:()=>({children:[],style:{},listeners:{},appendChild(n){this.children.push(n)},addEventListener(k,f){this.listeners[k]=f}})};
  let requests=[];
  const context=vm.createContext({document,QAPI:'',encodeURIComponent,
    fetch: (url,args) => new Promise(resolve => requests.push({url,args,resolve}))});
  const start=html.indexOf('var geoRequestVersion=');
  const end=html.indexOf('var natalASC=',start);
  assert(start>=0 && end>start);
  vm.runInContext(html.slice(start,end),context);
  const candidate={id:'one',latitude:55.75204,longitude:37.61781,address:'Москва',changes:[]};
  const result={token:'token',message:'Выберите место',candidates:[candidate]};
  const confirmed={status:'confirmed',latitude:55.75204,longitude:37.61781,gmt:3,timezone_name:'Europe/Moscow',address:'Москва'};
  const respond=(index,data=result)=>requests[index].resolve({ok:true,json:async()=>data});
  const button=()=>nodes.geo.children.at(-1).children.at(-1);
  const input=(id,value) => {nodes[id].value=value;nodes[id].listeners.input();};
  const run=(js)=>vm.runInContext(js,context);
  vm.runInContext(html.match(/^function pInt.+$/m)[0]+'\n'+html.match(/^function gI.+$/m)[0]+'\n'+html.slice(html.indexOf('function checkBirthData('),html.indexOf('function gmtToTz(')),context);
  vm.runInContext(html.match(/^function gmtToTz.+$/m)[0],context);
  assert.equal(run("gmtToTz('+5.5')"),null);
  assert.equal(run("gmtToTz('+5.75')"),null);
  assert.equal(run("gmtToTz('-3.5')"),null);
  assert.equal(run("gmtToTz('+3')"),'Etc/GMT-3');
  nodes.dt.value='30.01.1961';nodes.tm.value='12:30:00';nodes.la.value='55';nodes.lo.value='37';nodes.tz.value='+3';
  assert.equal(run('chkI(gI())'),null);
  nodes.dt.value='30.02.1961';assert.match(run('chkI(gI())'),/не существует/);
  nodes.dt.value='30.01.1961';nodes.tm.value='24:00';assert.match(run('chkI(gI())'),/время/);
  nodes.tm.value='12abc:30';assert.match(run('chkI(gI())'),/время/);
  nodes.tm.value='';assert.equal(run('chkI(gI())'),null,'Unknown birth time remains supported');
  nodes.la.value='91';assert.match(run('chkI(gI())'),/координат/);
  nodes.la.value='55';nodes.tz.value='';assert.match(run('chkI(gI())'),/GMT/);
  nodes.tz.value='1e1';assert.match(run('chkI(gI())'),/GMT/);
  nodes.tm.value='12:30';nodes.tz.value='+3';
  nodes.pl.value='Москва';nodes.cn.value='Россия';nodes.dt.value='30.01.1961';
  const first=run("geoFind('me')");
  assert.equal(requests[0].url,'/api/location-check/search');
  assert.equal(JSON.parse(requests[0].args.body).country,'Россия');
  respond(0);await first;
  assert.equal(nodes.la.value,'','Search must not adopt coordinates before explicit choice');
  const confirm=button().listeners.click();
  assert.equal(JSON.parse(requests[1].args.body).date,'1961-01-30');
  respond(1,confirmed);await confirm;
  assert.equal(nodes.la.value,55.75204);assert.equal(nodes.pl.dataset.tz,'Europe/Moscow');
  input('pl','Ижевск');assert.equal(nodes.la.value,'');assert.equal(nodes.pl.dataset.tz,'');
  const old=run("geoFind('me')");input('pl','Казань');respond(2);await old;
  assert.equal(nodes.la.value,'','Old search cannot adopt coordinates');
  const failed=run("geoFind('me')");respond(3,{status:'unavailable',message:'Нет связи'});await failed;
  assert.equal(nodes.la.value,'');assert.match(nodes.st.textContent,/Нет связи/);
  const pending=run("geoFind('me')");respond(4);await pending;
  const lateConfirm=button().listeners.click();input('dt','31.01.1961');respond(5,confirmed);await lateConfirm;
  assert.equal(nodes.la.value,'','Changed birth date rejects delayed confirmation');
  nodes.ppl.value='Москва';nodes.pcn.value='Россия';nodes.pd.value='30.01.1961';
  const partner=run("geoFind('pt')");respond(6);await partner;
  assert.equal(nodes.py.value,'');assert.equal(run('geoRequestVersion.partner'),1);
  const partnerButton=nodes.geoP.children.at(-1).children.at(-1);
  const partnerConfirm=partnerButton.listeners.click();respond(7,confirmed);await partnerConfirm;
  assert.equal(nodes.py.value,55.75204);input('pcn','Казахстан');assert.equal(nodes.py.value,'');
  assert.match(run('polarWarn(78)'),/РЕГИОНМОНТАНУ/);
  assert.equal(run("geoEscape('<script>')"),'&lt;script&gt;');
  console.log(`${filename}: inline syntax (${scripts} scripts), input validation, unknown birth time, success, city change, stale response, failure, racing searches, manual GMT, partner, date change — passed`);
}
(async()=>{await check('index.html');await check('prognoz.html');})().catch(e=>{console.error(e);process.exitCode=1;});
