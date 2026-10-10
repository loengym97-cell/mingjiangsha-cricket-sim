'use strict';
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let runId = Number(new URLSearchParams(location.search).get('run')) || 0;
let currentRun = null, currentPage = 1, total = 0, detail = null, step = 0, timer = null;
let listEpoch = 0, detailEpoch = 0, followingJob = false, lastJobRunning = false;
let rosterKey='';
let versionsKey='';
let aiVersions={},aiChoices={};
function refreshAi(side) {
  const select=$(`${side}_ai`), current=select.value;
  const choices=aiChoices[$(side).value]||Object.keys(aiVersions);
  select.replaceChildren(...choices.map(key=>new Option(aiVersions[key],key)));
  if(choices.includes(current))select.value=current;
}

async function api(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `请求失败 (${response.status})`);
  return data;
}
function message(text, error=false) { $('message').textContent=text; $('message').classList.toggle('error',error); }
function names() { return currentRun ? [currentRun.params.left,currentRun.params.right] : ['左侧武将','右侧武将']; }
function sideName(side) { return side === -2 ? '未结束' : side === -1 ? '同时阵亡' : `${names()[side]}（${side===0?'左':'右'}）`; }
function stopPlay() { clearInterval(timer); timer=null; $('play').textContent='自动播放'; }

function renderSummary(run) {
  currentRun = run;
  $('export').hidden = !run || run.status !== 'complete';
  if (!run) return;
  $('export').href = `/reports/run_${run.id}.csv`;
  $('rulesContent').replaceChildren();
  const ruleGroups = [['已确认规则',run.rules.confirmed],['待确认的边界',run.rules.pending_interactions],['当前采用的假设',run.rules.diagnostic_assumptions]];
  for (const [title,values] of ruleGroups) {
    const heading=document.createElement('h3'); heading.textContent=title; $('rulesContent').append(heading);
    for (const [key,value] of Object.entries(values || {})) {
      const p=document.createElement('p'); p.textContent=Array.isArray(values)?String(value):`${key}：${typeof value==='object'?JSON.stringify(value):value}`;
      $('rulesContent').append(p);
    }
  }
  const s=run.summary;
  if (!s) { $('summary').textContent=`第 ${run.id} 批已完成 ${run.completed.toLocaleString()} / ${run.params.games.toLocaleString()} 局。${run.error||''}`; return; }
  const n=s.params.games, counts=s.counts, wins=side=>Number(counts[String(side)]||0);
  const rows=[0,1].map(side=>`<tr><td>${esc(sideName(side))}</td><td>${wins(side).toLocaleString()}</td><td>${(100*wins(side)/n).toFixed(2)}%</td></tr>`).join('');
  const firstRows=[0,1].map(side=>{
    const group=s.by_first[String(side)]; const groupN=Object.values(group).reduce((a,b)=>a+b,0);
    return `<tr><td>${esc(sideName(side))}先手</td><td>${groupN.toLocaleString()}</td><td>${group['0']||0}</td><td>${group['1']||0}</td></tr>`;
  }).join('');
  const legacy=(s.rules.revision||0)<4;
  $('summary').innerHTML=`${legacy?'<p class="notice"><strong>旧规则批次：距离等规则尚未修正，请以最新修正批次为准。</strong></p>':''}<p>第 ${run.id} 批 · <strong>${n.toLocaleString()} 局</strong> · 平均 ${s.mean_rounds.toFixed(2)} 轮 · ${esc(s.created)}</p>
    <p class="muted">左侧 AI ${esc(s.params.left_ai||'v1')} / 技能 ${esc(s.params.left_version||'v1')} · 右侧 AI ${esc(s.params.right_ai||'v1')} / 技能 ${esc(s.params.right_version||'v1')}</p>
    <div class="winbar" aria-hidden="true"><span class="left-win" style="width:${100*wins(0)/n}%"></span><span class="right-win" style="width:${100*wins(1)/n}%"></span><span class="other-win" style="width:${100*(wins(-1)+wins(-2))/n}%"></span></div>
    <table class="summary-table"><thead><tr><th>武将</th><th>获胜局数</th><th>占全部对局</th></tr></thead><tbody>${rows}</tbody></table>
    <p class="muted">未结束 ${wins(-2)} 局${wins(-1)?` · 旧模型双方死亡 ${wins(-1)} 局`:''} · 种子 ${s.params.seed} · 先手轮换均衡分配</p>
    <table class="summary-table"><thead><tr><th>先手分组</th><th>局数</th><th>${esc(names()[0])}获胜</th><th>${esc(names()[1])}获胜</th></tr></thead><tbody>${firstRows}</tbody></table>`;
}

async function loadGames() {
  const epoch=++listEpoch;
  if (!runId) return;
  const query=new URLSearchParams({run:runId,page:currentPage,winner:$('winner').value,first:$('first').value});
  if ($('gameFilter').value) query.set('game',$('gameFilter').value);
  const data=await api('/api/games?'+query);
  if (epoch!==listEpoch) return;
  total=data.total;
  $('total').textContent=`${total.toLocaleString()} 局`;
  $('pageInfo').textContent=`第 ${currentPage} / ${Math.max(1,Math.ceil(total/50))} 页`;
  $('prev').disabled=currentPage<=1; $('next').disabled=currentPage*50>=total;
  $('gameRows').innerHTML=data.rows.length ? data.rows.map(row=>`<tr data-game="${row.id}" class="${detail?.id===row.id?'selected':''}">
    <td>${row.id}</td><td>${esc(sideName(row.winner_side))}</td><td>${esc(names()[row.first_side])}</td><td>${row.rounds}</td><td><button data-open="${row.id}" aria-label="查看第${row.id}局">查看</button></td></tr>`).join('') : '<tr><td colspan="5">没有符合条件的对局，请调整筛选条件。</td></tr>';
}

async function selectGame(id) {
  const epoch=++detailEpoch; stopPlay();
  $('detailMeta').textContent=`正在读取第 ${id} 局…`;
  const data=await api(`/api/detail?run=${runId}&game=${id}`);
  if (epoch!==detailEpoch) return;
  detail=data; step=0; $('logSearch').value=''; $('replay').hidden=false; $('downloadDetail').disabled=false;
  $('detailTitle').textContent=`第 ${id} 局详情`;
  $('detailMeta').textContent=`${sideName(data.result.winner_side)} · ${data.result.rounds} 轮 · ${names()[data.result.first_side]}先手 · 种子 ${data.seed}`;
  $('step').max=Math.max(0,data.events.length-1);
  document.querySelectorAll('[data-game]').forEach(row=>row.classList.toggle('selected',Number(row.dataset.game)===id));
  renderStep();
}
function cardHTML(card) { return `<span class="card ${['♥','♦'].includes(card.suit)?'red':''}" title="牌ID ${card.id}">${esc(card.suit)}${card.rank} ${esc(card.name)}</span>`; }
function renderStep() {
  if (!detail || !detail.events.length) return;
  const event=detail.events[step], state=event.state;
  $('step').value=step; $('stepLabel').textContent=`${step+1} / ${detail.events.length}`;
  $('stepPrev').disabled=step<=0; $('stepNext').disabled=step>=detail.events.length-1;
  $('currentEvent').textContent=`${event.turn===0?'开局':`第 ${Math.ceil(event.turn/2)} 轮 / 第 ${event.turn} 个回合`} · ${event.text}`;
  $('board').innerHTML=state.players.map((p,side)=>`<article class="player"><h3>${esc(p.name)} <span class="muted">${side===0?'左侧':'右侧'}</span> <span class="hp">${p.hp} / ${p.max_hp??6} 体力</span></h3>
    <p class="muted">${[p.chained?'横置':'未横置',p.silenced?'技能封禁':'',p.frozen?'霜冻限制':'',`留牌 ${p.hand_limit??3}`,`距离 ${p.distance_to_other??'未启用'}`,`范围 ${p.attack_range??'未启用'}`].filter(Boolean).join(' · ')}</p>
    <dl><dt>手牌 ${p.hand.length} 张</dt><dd>${p.hand.map(cardHTML).join('')||'无'}</dd><dt>装备 ${p.equipment.length} 件</dt><dd>${p.equipment.map(cardHTML).join('')||'无'}</dd><dt>卜卦区</dt><dd>${p.delayed.map(cardHTML).join('')||'无'}</dd></dl></article>`).join('');
  $('pileState').textContent=`牌堆 ${state.deck} · 弃牌 ${state.discard} · 移出游戏 ${state.burned}`;
  renderEvents();
}
function renderEvents() {
  if (!detail) return;
  const query=$('logSearch').value.trim();
  let indices=detail.events.map((_,i)=>i);
  if (query) indices=indices.filter(i=>detail.events[i].text.includes(query));
  else indices=indices.slice(Math.max(0,step-100),Math.min(detail.events.length,step+200));
  $('events').innerHTML=indices.map(i=>`<li><button data-step="${i}" class="${i===step?'selected':''}"><small>${i+1} · 回合 ${detail.events[i].turn}</small>${esc(detail.events[i].text)}</button></li>`).join('') || '<li>没有匹配事件。</li>';
}

async function loadRuns() {
  const runs=await api('/api/runs');
  $('runs').innerHTML=runs.length ? runs.map(r=>{
    const params=JSON.parse(r.params); const labels={complete:'完成',running:'运行中',failed:'失败',interrupted:'中断'};
    return `<option value="${r.id}">第${r.id}批 · ${esc(params.left)} vs ${esc(params.right)} · ${r.completed}局 · ${labels[r.status]||r.status}</option>`;
  }).join('') : '<option value="">暂无记录</option>';
  if (runId) $('runs').value=runId;
}
async function refresh() {
  const status=await api('/api/status'+(runId?`?run=${runId}`:''));
  const job=status.job;
  const versionData=JSON.stringify([status.ai_versions,status.skill_versions]);
  if(versionsKey!==versionData && status.ai_versions) {
    versionsKey=versionData;
    aiVersions=status.ai_versions; aiChoices=status.ai_choices||{};
    for(const side of ['left','right']) for(const type of ['ai','version']) {
      const select=$(`${side}_${type}`), current=select.value;
      const options=type==='ai'?status.ai_versions:status.skill_versions;
      select.replaceChildren(...Object.entries(options).map(([key,label])=>new Option(label,key)));
      if(current in options)select.value=current;
    }
    for(const side of ['left','right'])refreshAi(side);
  }
  if(rosterKey!==JSON.stringify(status.characters)) {
    rosterKey=JSON.stringify(status.characters);
    for(const id of ['left','right']) {
      const current=$(id).value;
      $(id).replaceChildren(...status.characters.map(name=>new Option(name,name)));
      if(status.characters.includes(current))$(id).value=current;
    }
  }
  if (!runId && status.run) runId=status.run.id;
  if (followingJob && job.run_id) runId=job.run_id;
  $('runButton').disabled=job.running;
  $('runButton').textContent=job.running?'正在模拟…':'开始模拟';
  $('progress').hidden=!job.running; $('progress').value=job.total?100*job.completed/job.total:0;
  if (job.running) message(`正在运行：${job.completed.toLocaleString()} / ${job.total.toLocaleString()} 局，完整记录持续写入本地。`);
  else if (job.error) message(`运行失败：${job.error}。已完成记录仍可查询。`,true);
  else message(status.run ? `第 ${status.run.id} 批 · 已保存 ${status.run.completed.toLocaleString()} 局详情` : '选择武将和局数后开始模拟。');
  let run=status.run;
  if (runId && run?.id!==runId) run=(await api(`/api/status?run=${runId}`)).run;
  if (run) renderSummary(run);
  if (job.running || lastJobRunning) { await loadRuns(); await loadGames(); }
  lastJobRunning=job.running;
  if (followingJob && !job.running) followingJob=false;
}

$('runForm').addEventListener('submit',async event=>{
  event.preventDefault(); stopPlay(); $('runButton').disabled=true;
  try {
    const params=Object.fromEntries(new FormData(event.currentTarget));
    for(const key of ['games','seed','max_rounds']) params[key]=Number(params[key]);
    await api('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(params)});
    followingJob=true; runId=0; currentPage=1; detail=null; $('replay').hidden=true; $('downloadDetail').disabled=true;
    $('winner').value=''; $('first').value=''; $('gameFilter').value='';
    message('任务已开始，正在保存逐局详情。'); await refresh();
  } catch(error) { message(error.message,true); $('runButton').disabled=false; }
});
function safely(fn) { return (...args)=>Promise.resolve().then(()=>fn(...args)).catch(error=>message(error.message,true)); }
for(const side of ['left','right']) $(side).addEventListener('change',()=>refreshAi(side));
$('runs').addEventListener('change',safely(async()=>{
  runId=Number($('runs').value); followingJob=false; currentPage=1; detail=null; ++detailEpoch; stopPlay();
  $('replay').hidden=true; $('downloadDetail').disabled=true; $('detailTitle').textContent='对局详情';
  $('detailMeta').textContent='选择左侧任意一局，查看每次出牌和技能结算。';
  await refresh(); await loadGames();
}));
$('filterButton').addEventListener('click',safely(async()=>{currentPage=1;await loadGames();}));
for(const id of ['winner','first']) $(id).addEventListener('change',safely(async()=>{currentPage=1;await loadGames();}));
$('gameFilter').addEventListener('keydown',event=>{if(event.key==='Enter') $('filterButton').click();});
$('prev').addEventListener('click',safely(async()=>{if(currentPage>1){currentPage--;await loadGames();}}));
$('next').addEventListener('click',safely(async()=>{if(currentPage*50<total){currentPage++;await loadGames();}}));
$('gameRows').addEventListener('click',safely(async event=>{const button=event.target.closest('[data-open]');if(button)await selectGame(Number(button.dataset.open));}));
$('events').addEventListener('click',event=>{const button=event.target.closest('[data-step]');if(button){stopPlay();step=Number(button.dataset.step);renderStep();}});
$('step').addEventListener('input',()=>{stopPlay();step=Number($('step').value);renderStep();});
$('stepPrev').addEventListener('click',()=>{stopPlay();step=Math.max(0,step-1);renderStep();});
$('stepNext').addEventListener('click',()=>{stopPlay();step=Math.min(detail.events.length-1,step+1);renderStep();});
$('play').addEventListener('click',()=>{
  if(timer)return stopPlay();
  if(step>=detail.events.length-1)step=0;
  $('play').textContent='暂停播放'; timer=setInterval(()=>{if(step>=detail.events.length-1)return stopPlay();step++;renderStep();},650);
});
$('logSearch').addEventListener('input',renderEvents);
$('downloadDetail').addEventListener('click',()=>{
  if(!detail)return;
  const url=URL.createObjectURL(new Blob([JSON.stringify(detail,null,2)],{type:'application/json;charset=utf-8'}));
  const a=document.createElement('a');a.href=url;a.download=`run_${runId}_game_${detail.id}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
(async()=>{try{await refresh();await loadRuns();await loadGames();}catch(error){message(error.message,true);}finally{setInterval(()=>refresh().catch(error=>message(error.message,true)),2000);}})();
