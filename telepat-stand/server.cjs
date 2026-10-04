const http=require('http'),crypto=require('crypto'),fs=require('fs'),path=require('path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const password=process.env.STAND_PASSWORD;
if(!password||password.length<24)throw Error('STAND_PASSWORD must contain at least 24 characters');
const ticket=crypto.randomBytes(32).toString('hex');let browser,page,queue=Promise.resolve(),starting,framePending,lastFrame;
const fixture=process.env.STAND_FIXTURE==='1';
const login='<!doctype html><meta charset="utf-8"><title>Телепат — закрытый стенд</title><h2>Закрытый испытательный стенд</h2><form method="post" action="/login"><input type="password" name="password" autocomplete="off" aria-label="Пароль стенда"><button>Войти</button></form>';
async function body(req){let data='';for await(const chunk of req){data+=chunk;if(Buffer.byteLength(data)>16000)throw Error('Input too large');}return data;}
function equal(a,b){const x=Buffer.from(a),y=Buffer.from(b);return x.length===y.length&&crypto.timingSafeEqual(x,y);}
async function start(){if(starting)return starting;if(browser&&page&&!page.isClosed())return;starting=initialize().finally(()=>{starting=null;});return starting;}
function configure(p){p.setDefaultTimeout(5000);p.setDefaultNavigationTimeout(15000);p.on('dialog',d=>d.dismiss().catch(()=>{}));}
async function initialize(){if(browser)await browser.close();browser=await chromium.launch({headless:true,...(process.env.STAND_CHANNEL?{channel:process.env.STAND_CHANNEL}:{chromiumSandbox:true})});
 const context=await browser.newContext({viewport:{width:1100,height:760}});
 await require('./register.cjs')(context);
 page=await context.newPage();
 configure(page);context.on('page',p=>{configure(p);page=p;p.on('close',()=>{page=context.pages().find(x=>!x.isClosed());});});
 if(fixture)await page.setContent('<meta charset="utf-8"><style>body{background:#071224;color:white;font:22px Arial}input{padding:16px}button{padding:16px}</style><h2>Тестовый чат</h2><div id="messages">Начальное сообщение</div><input aria-label="Сообщение"><button onclick="messages.textContent+=document.querySelector(\'input\').value">Отправить</button>');
 else await page.goto('https://copilot.com/chat',{waitUntil:'domcontentloaded',timeout:60000});
}
const viewer=fs.readFileSync(path.join(__dirname,'viewer.html'),'utf8');
const server=http.createServer(async(req,res)=>{res.setHeader('Cache-Control','no-store');res.setHeader('X-Content-Type-Options','nosniff');res.setHeader('Referrer-Policy','no-referrer');res.setHeader('X-Frame-Options','SAMEORIGIN');
 try{
  if(req.url==='/health'){res.end('ok');return;}
  if(req.url==='/login'&&req.method==='POST'){const supplied=new URLSearchParams(await body(req)).get('password')||'';
   if(!equal(supplied,password)){res.writeHead(403,{'Content-Type':'text/html; charset=utf-8'});res.end(login);return;}
   res.setHeader('Set-Cookie',`stand=${ticket}; HttpOnly; SameSite=Strict; Path=/; Max-Age=3600${fixture?'':'; Secure'}`);res.writeHead(303,{Location:'/'});res.end();return;
  }
  if(!(req.headers.cookie||'').split(';').some(x=>equal(x.trim(),`stand=${ticket}`))){res.writeHead(401,{'Content-Type':'text/html; charset=utf-8'});res.end(login);return;}
  if(req.method==='GET'&&req.url==='/'){res.setHeader('Content-Type','text/html; charset=utf-8');res.end(viewer);return;}
  if(req.method==='GET'&&req.url==='/status'){
   const state={version:'17',page:'starting',autoload:'waiting',mounts:0,mask:false,editor:false};
   if(page&&!page.isClosed()){
    const hostname=new URL(page.url()).hostname;
    state.page=['copilot.com','www.copilot.com'].includes(hostname)?'copilot':/^(login\.live\.com|login\.microsoftonline\.com|account\.live\.com)$/.test(hostname)?'sign-in':'other';
    if(state.page==='copilot')Object.assign(state,await page.evaluate(()=>({autoload:document.documentElement.dataset.telepatAutoload||'not-loaded',mounts:Number(document.documentElement.dataset.telepatMounts||0),mask:!!document.getElementById('telepat-v7-clean'),editor:!!document.getElementById('m365-chat-editor-target-element')})));
   }
   res.setHeader('Content-Type','application/json; charset=utf-8');res.end(JSON.stringify(state));return;
  }
  if(req.method==='GET'&&req.url==='/frame'){
   await start();if(!framePending)framePending=page.screenshot({type:'jpeg',quality:65,timeout:5000}).then(b=>{lastFrame=b;return b;}).finally(()=>{framePending=null;});
   const b=await framePending;res.setHeader('Content-Type','image/jpeg');res.end(b);return;
  }
  const job=queue.then(async()=>{
   await start();if(!page||page.isClosed())throw Error('Browser page closed');
   if(fixture&&req.method==='GET'&&req.url==='/test-state'){res.end(await page.locator('#messages').innerText());return;}
   if(fixture&&req.method==='POST'&&req.url==='/test-dialog'&&req.headers['x-stand-action']==='1'){await page.evaluate(()=>alert('Fixture dialog'));res.end('ok');return;}
   if(req.method!=='POST'||req.headers['x-stand-action']!=='1'){res.writeHead(405);res.end();return;}
   const data=JSON.parse(await body(req));
   if(req.url==='/click'){if(!Number.isFinite(data.x)||!Number.isFinite(data.y)||data.x<0||data.y<0||data.x>1100||data.y>760)throw Error('Invalid coordinates');await page.mouse.click(data.x,data.y);}
   else if(req.url==='/text'){if(typeof data.text!=='string'||data.text.length>8000)throw Error('Invalid text');await page.keyboard.insertText(data.text);}
   else if(req.url==='/key'){if(!['Enter','Backspace','Tab','Escape','ArrowDown','ArrowUp'].includes(data.key))throw Error('Invalid key');await page.keyboard.press(data.key);}
   else if(req.url==='/wheel'){if(!Number.isFinite(data.dy)||Math.abs(data.dy)>2000)throw Error('Invalid scroll');await page.mouse.wheel(0,data.dy);}
   else if(req.url==='/mask'){if(new URL(page.url()).hostname!=='copilot.com')throw Error('Open Copilot before applying mask');await page.evaluate(fs.readFileSync(path.join(__dirname,'mask.js'),'utf8'));if(!await page.locator('#telepat-v7-clean').count())throw Error('Mask prerequisites not found');}
   else{res.writeHead(404);res.end();return;}
   res.end('ok');
  });queue=job.catch(()=>{});await job;
 }catch(e){if(!res.headersSent)res.writeHead(503,{'Content-Type':'text/plain; charset=utf-8'});res.end('Стенд пока не готов. Повторите позже.');console.error('Stand operation failed; details omitted to protect authentication data');}
});
server.listen(Number(process.env.PORT||8780),'0.0.0.0',()=>console.log('Telepat stand listening'));
process.on('SIGTERM',async()=>{server.close();if(browser)await browser.close();process.exit();});
