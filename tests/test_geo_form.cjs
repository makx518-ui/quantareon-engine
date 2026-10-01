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
    addEventListener(event, fn){this.listeners[event]=fn;}
  }]));
  const document = {getElementById: id => nodes[id] || null};
  let requests=[];
  const context=vm.createContext({document,QAPI:'',encodeURIComponent,
    fetch: url => new Promise(resolve => requests.push({url,resolve}))});
  const start=html.indexOf('var geoRequestVersion=');
  const end=html.indexOf('var natalASC=',start);
  assert(start>=0 && end>start);
  vm.runInContext(html.slice(start,end),context);
  const result={latitude:55.75204,longitude:37.61781,utc_offset:3,timezone_name:'Europe/Moscow',address:'Москва',admin:{}};
  const respond=(index, ok=true) => requests[index].resolve({ok,json:async()=>ok?result:{detail:'Не найдено'}});
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
  assert.match(requests[0].url,/on_date=1961-01-30/);
  respond(0);await first;
  assert.equal(nodes.la.value,55.75204);
  assert.equal(nodes.pl.dataset.tz,'Europe/Moscow');
  input('pl','Ижевск');
  assert.equal(nodes.la.value,'');assert.equal(nodes.lo.value,'');assert.equal(nodes.tz.value,'');
  assert.equal(nodes.pl.dataset.tz,'');assert.equal(nodes.geo.style.display,'none');
  const old=run("geoFind('me')");
  input('pl','Казань');
  respond(1);await old;
  assert.equal(nodes.la.value,'','Delayed old city must not overwrite input');
  const failed=run("geoFind('me')");respond(2,false);await failed;
  assert.equal(nodes.la.value,'','Failed lookup must leave no old coordinates');
  nodes.pl.value='Москва';const slow=run("geoFind('me')");const latest=run("geoFind('me')");
  respond(4);await latest;respond(3,false);await slow;
  assert.equal(nodes.la.value,55.75204);assert.match(nodes.st.textContent,/Москва/);
  input('tz','+5.5');assert.equal(nodes.pl.dataset.tz,'');
  nodes.ppl.dataset.tz='Europe/Moscow';nodes.py.value='55';
  input('pcn','Россия');assert.equal(nodes.py.value,'');assert.equal(nodes.ppl.dataset.tz,'');
  nodes.pl.value='Москва';const dated=run("geoFind('me')");input('dt','31.01.1961');
  respond(5);await dated;assert.equal(nodes.la.value,'');
  console.log(`${filename}: inline syntax (${scripts} scripts), input validation, unknown birth time, success, city change, stale response, failure, racing searches, manual GMT, partner, date change — passed`);
}
(async()=>{await check('index.html');await check('prognoz.html');})().catch(e=>{console.error(e);process.exitCode=1;});
