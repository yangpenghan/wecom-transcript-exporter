'use strict';
const $ = id => document.getElementById(id);
const state = {health:null, path:'', rooms:[], selected:null, busy:false, connected:false, result:null};
const text = (id,value) => { $(id).textContent=value; };
function errorNotice(error){text('notice-title',(error instanceof TypeError?'无法连接本地应用，请重新打开程序。':error.message)||'本次操作未完成。');text('notice-action',error.action||'请重试或重新打开应用。');$('notice').hidden=false;$('notice').scrollIntoView({block:'nearest'});}
function setBusy(busy,stage='正在处理……'){
  state.busy=busy;$('progress').hidden=!busy;text('progress-text',stage);
  document.querySelectorAll('button:not(#help-button):not(#close-help):not(#dismiss-notice)').forEach(b=>b.disabled=busy);
  document.querySelectorAll('input').forEach(input=>input.disabled=busy);
  if(!busy){$('connect').disabled=!state.path||!$('consent').checked||!state.health?.windows||!state.health?.crypto||!state.health?.powershell;$('export').disabled=!state.selected;}
}
async function api(path,data){
  const response=await fetch('/api/'+path,{method:data===undefined?'GET':'POST',headers:data===undefined?{}:{'Content-Type':'application/json'},body:data===undefined?undefined:JSON.stringify(data),credentials:'same-origin'});
  const body=await response.json();if(!response.ok)throw body.error||{message:'无法连接本地应用，请重新打开程序。'};return body;
}
async function runJob(path,data,stage){
  $('notice').hidden=true;setBusy(true,stage);
  try{const {job}=await api(path,data);for(;;){const current=await api('job?id='+encodeURIComponent(job));if(current.state==='done')return current.result;if(current.state==='error')throw current.error;text('progress-text',current.stage||stage);await new Promise(resolve=>setTimeout(resolve,350));}}
  catch(error){errorNotice(error);return null;}finally{setBusy(false);}
}
function selectPath(path){
  state.path=path;$('manual-path').value=path;
  const remembered=state.health?.consented_databases?.includes(path);$('consent').checked=!!remembered;$('remembered-access').hidden=!remembered;
  document.querySelectorAll('.candidate input').forEach(input=>input.checked=input.value===path);
  text('selected-location','已选择：'+path);$('selected-location').hidden=[...document.querySelectorAll('.candidate input')].some(input=>input.value===path);setBusy(false);
}
function renderCandidates(result){
  const list=$('candidate-list');list.replaceChildren();const candidates=result.candidates||[];
  text('candidate-count',candidates.length===1?'找到 1 个账号':`找到 ${candidates.length} 个账号`);$('no-database').hidden=candidates.length>0;
  candidates.forEach((candidate,index)=>{const label=document.createElement('label');label.className='candidate';const radio=document.createElement('input');radio.type='radio';radio.name='database';radio.value=candidate.path;radio.addEventListener('change',()=>selectPath(candidate.path));const content=document.createElement('div');const title=document.createElement('strong');title.textContent=`企业微信账号 ${index+1}`;const path=document.createElement('p');path.textContent=candidate.path;const date=document.createElement('p');date.textContent='更新于 '+new Date(candidate.modified*1000).toLocaleString('zh-CN');content.append(title,path,date);label.append(radio,content);list.append(label);});
  state.path='';$('selected-location').hidden=true;$('consent').checked=false;$('remembered-access').hidden=true;
  if(candidates.length===1)selectPath(candidates[0].path);
  else if(candidates.some(c=>c.path===state.health?.saved_database))selectPath(state.health.saved_database);
  if(result.truncated)errorNotice({message:'文件夹查找已达到范围或时间上限。',action:'请选择更具体的企业微信存储文件夹后重试。'});
  setBusy(false);
}
async function discover(root=''){const result=await runJob('discover',{root},'正在查找本机的企业微信数据……');if(result)renderCandidates(result);}
async function browse(kind){const result=await runJob('browse',{kind},'请在 Windows 对话框中选择位置……');if(!result?.path)return;if(kind==='output')$('output-folder').value=result.path;else if(kind==='search')await discover(result.path);else{selectPath(result.path);text('candidate-count','已手动选择位置');$('no-database').hidden=true;}}
function showRecordings(result){state.connected=true;state.rooms=result.rooms;state.selected=null;state.result=null;$('export-result').hidden=true;$('setup-view').hidden=true;$('recordings-view').hidden=false;text('connected-path',result.database);text('selected-title','请从左侧列表选择一条记录');text('selected-date','');document.querySelectorAll('.journey li').forEach(li=>{li.removeAttribute('aria-current');li.classList.add('complete');});$('step-export').setAttribute('aria-current','step');$('step-export').classList.remove('complete');$('recording-filter').value='';renderRooms();setBusy(false);}
async function connect(){const result=await runJob('connect',{path:state.path,consent:$('consent').checked},'正在连接所选的企业微信账号……');if(result){state.health=await api('health');showRecordings(result);}else{setupView();}}
function renderRooms(){
  const filter=$('recording-filter').value.trim().toLocaleLowerCase();const rooms=state.rooms.filter(r=>r.title.toLocaleLowerCase().includes(filter));text('recording-count',`显示 ${rooms.length} 条，共 ${state.rooms.length} 条本地记录`);$('recording-list').replaceChildren();$('empty-recordings').hidden=rooms.length>0;text('empty-recordings-message',state.rooms.length?'没有匹配的标题，请换一个关键词。':'请在企业微信中打开面聊记录，等待加载完成后刷新列表。');
  rooms.forEach(room=>{const button=document.createElement('button');button.type='button';button.className='recording';button.setAttribute('aria-pressed',String(state.selected?.room_id===room.room_id));const title=document.createElement('strong');title.textContent=room.title;const date=document.createElement('span');date.textContent=new Date(room.started*1000).toLocaleString('zh-CN');button.append(title,date);button.addEventListener('click',()=>{state.selected=room;state.result=null;$('export-result').hidden=true;text('selected-title',room.title);text('selected-date',date.textContent);renderRooms();setBusy(false);});$('recording-list').append(button);});
}
function showResult(result){state.result=result;$('export-result').hidden=false;text('result-summary',`${result.passages} 段原文 · 用时 ${result.elapsed.toFixed(2)} 秒${result.speaker_resolution?.resolved?' · 已补全 '+result.speaker_resolution.resolved+' 位成员姓名':''}`);text('result-filename',result.markdown);$('result-warnings').replaceChildren();result.warnings.forEach(warning=>{const li=document.createElement('li');li.textContent=warning;$('result-warnings').append(li);});$('result-warnings').hidden=!result.warnings.length;$('download-md').href='/api/download?id='+encodeURIComponent(result.id)+'&kind=md';$('download-json').href='/api/download?id='+encodeURIComponent(result.id)+'&kind=json';text('preview-caption',result.preview_truncated?'这里展示前 30 段，保存的文件包含本次导出的全部原文。':'以下展示本次导出的全部原文。');$('preview-text').replaceChildren();result.preview.forEach(record=>{const item=document.createElement('div');item.className='utterance';const label=document.createElement('strong');label.textContent=record.speaker+' · '+record.time;const words=document.createElement('p');words.textContent=record.text;item.append(label,words);$('preview-text').append(item);});}
function setupView(){$('resolve-speakers').checked=false;state.connected=false;state.selected=null;state.rooms=[];$('setup-view').hidden=false;$('recordings-view').hidden=true;document.querySelectorAll('.journey li').forEach(li=>{li.removeAttribute('aria-current');li.classList.remove('complete');});$('step-device').classList.add('complete');$('step-location').setAttribute('aria-current','step');setBusy(false);}
async function initialize(){
  try{const token=location.hash.slice(1);if(token){history.replaceState(null,'',location.pathname);await api('session',{token});}state.health=await api('health');$('output-folder').value=state.health.output_folder;$('checks').replaceChildren();
    for(const [okay,label] of [[state.health.windows,'Windows 系统'],[state.health.crypto,'导出组件就绪'],[state.health.powershell,'本地读取组件就绪'],[null,'企业微信：请登录自己的账号']]){const li=document.createElement('li');li.textContent=label;li.className=okay===false?'failed':okay===null?'pending':'';$('checks').append(li);}
    if(!state.health.windows||!state.health.crypto||!state.health.powershell){errorNotice({message:'此电脑缺少必要组件。',action:'请使用完整的 Windows 便携包。源码版请先运行 Setup.cmd。如缺少 Windows PowerShell，请联系 IT。'});setBusy(false);return;}
    $('step-device').classList.add('complete');await discover();setInterval(()=>api('heartbeat',{}).catch(()=>{}),15000);
  }catch(error){errorNotice(error);setBusy(true);$('progress').hidden=true;}
}
$('dismiss-notice').onclick=()=>$('notice').hidden=true;
$('help-button').onclick=()=>$('help-dialog').showModal();$('close-help').onclick=()=>$('help-dialog').close();
$('rescan').onclick=()=>discover();$('browse-database').onclick=()=>browse('database');$('browse-search').onclick=()=>browse('search');$('browse-output').onclick=()=>browse('output');
$('use-path').onclick=async()=>{const path=$('manual-path').value.trim().replace(/^"|"$/g,'');if(/voice_room5\.db$/i.test(path)){selectPath(path);text('candidate-count','已手动选择位置');}else await discover(path);};
$('consent').onchange=()=>{setBusy(false);$('step-location').removeAttribute('aria-current');$('step-access').removeAttribute('aria-current');$($('consent').checked?'step-access':'step-location').setAttribute('aria-current','step');};
$('connect').onclick=connect;$('refresh-recordings').onclick=connect;$('change-location').onclick=setupView;$('recording-filter').oninput=renderRooms;
$('export').onclick=async()=>{if(!state.selected)return;const result=await runJob('export',{room_id:state.selected.room_id,folder:$('output-folder').value,resolve_speakers:$('resolve-speakers').checked},'正在准备转录原文……');if(result)showResult(result);};
$('open-output').onclick=()=>api('open-folder',{id:state.result.id}).catch(errorNotice);
$('revoke').onclick=async()=>{const result=await runJob('revoke',{},'正在清除本地授权……');if(result){state.health=await api('health');$('consent').checked=false;$('remembered-access').hidden=true;$('help-dialog').close();setupView();errorNotice({message:'已清除本地授权。',action:'面聊数据和导出文件均已保留。再次连接时，请重新允许读取。'});}};
$('exit-button').onclick=async()=>{try{await api('exit',{});setBusy(true);$('progress').hidden=true;errorNotice({message:'应用已退出。',action:'可以关闭此页面。再次使用时，请重新打开程序。'});}catch(error){errorNotice(error);}};
initialize();
