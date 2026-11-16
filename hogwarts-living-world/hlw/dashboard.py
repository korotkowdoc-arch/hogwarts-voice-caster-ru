"""Read-only-first local diagnostics UI. No API keys are accepted or displayed."""
HTML = r'''<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hogwarts Living World — Control Room</title>
<style>
:root{color-scheme:dark;--bg:#11141a;--surface:#1b2029;--ink:#eaf0ef;--muted:#9caab5;--line:#303d46;--gold:#e6c67e;--ok:#83d3a0}
*{box-sizing:border-box}body{margin:0;font:15px/1.58 system-ui,-apple-system,Segoe UI,sans-serif;background:radial-gradient(ellipse 1100px 440px at 70% -100px,#28394d,transparent),var(--bg);color:var(--ink)}
main{max-width:1010px;margin:auto;padding:40px 20px 60px}h1{font:600 clamp(30px,5vw,45px)/1.17 Georgia,serif;margin:8px 0}h2{font-size:18px;margin:0 0 12px}p{margin:9px 0;color:var(--muted)}
.eyebrow{letter-spacing:.16em;color:var(--gold);font-size:12px;text-transform:uppercase}
.lead{font-size:16px;max-width:730px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,290px),1fr));gap:16px;margin:26px 0}
.panel{border:1px solid var(--line);background:var(--surface);border-radius:16px;padding:20px;min-width:0}
.info{display:grid;grid-template-columns:125px 1fr;gap:9px 6px}.info dt{color:var(--muted)}.info dd{margin:0;overflow-wrap:anywhere}
.status{display:inline-flex;gap:6px;align-items:center;border-radius:40px;background:#32453b;padding:3px 10px;color:#bdeccf;font-size:12px}
.warning{background:#3c3326;color:#f1ce8d}.faded{color:var(--muted)}
textarea,input,select,button{font:inherit}input,textarea,select{width:100%;background:#10161e;color:var(--ink);border:1px solid #47545d;padding:12px;border-radius:9px}
textarea{min-height:80px;resize:vertical}label{display:block;font-size:13px;color:var(--muted);margin:12px 0 5px}
.actions{display:flex;flex-wrap:wrap;gap:9px;margin-top:13px}button{background:#dac089;color:#1d2125;border:none;padding:10px 16px;border-radius:9px;cursor:pointer;font-weight:650}button.secondary{background:#33414e;color:var(--ink)}button:hover{filter:brightness(1.08)}button:disabled{opacity:.4;cursor:progress}
pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#121820;border:1px solid var(--line);padding:12px;border-radius:9px;min-height:54px}
small,footer{color:var(--muted)}.npcrow{display:flex;justify-content:space-between;gap:12px;border-bottom:1px solid var(--line);padding:10px 0}
.npcrow:last-child{border-bottom:none}.meters{font-variant-numeric:tabular-nums}.full{grid-column:1/-1}
code{color:var(--gold)}.mutedtitle{color:var(--muted);font-size:13px}
@media(max-width:620px){main{padding:24px 14px}.info{grid-template-columns:1fr}.info dd{margin:-8px 0 8px}}
</style>
</head>
<body><main>
<div class="eyebrow">Hogwarts Living World / экспериментальный мост</div>
<h1>Комната управления</h1>
<p class="lead">Здесь мы проверяем ИИ, память персонажей и связь с UE4SS. Настоящие игровые задания и письма пока не запускаются. Никто не потратит деньги через платный запасной API — его нет.</p>
<section class="grid">
<div class="panel"><h2>Состояние моста</h2><dl class="info">
<dt>Версия</dt><dd id="version">...</dd>
<dt>Текстовый ИИ</dt><dd id="providers">...</dd>
<dt>Осталось вызовов сегодня</dt><dd id="quotas">...</dd>
<dt>Игровой мод</dt><dd><span class="status warning">не подтверждён</span></dd>
<dt>Последний UE4SS сигнал</dt><dd id="probe">пока нет</dd>
<dt>База памяти</dt><dd id="db">...</dd>
</dl><div class="actions"><button class="secondary" id="refresh">Обновить статус</button></div></div>
<div class="panel"><h2>Проверить облачный диалог</h2>
<p>Только одна фраза за раз. Отправка расходует бесплатный лимит API; если он исчерпан — будет ошибка, без платного обхода.</p>
<label for="message">Сообщение Себастьяну</label>
<textarea id="message" maxlength="900">Привет, Себастьян. О чём ты сегодня думаешь?</textarea>
<div class="actions"><button id="say">Получить ответ ИИ</button></div>
<pre id="reply" aria-live="polite">Ответ появится здесь.</pre>
</div>
<div class="panel full"><h2>Память персонажей</h2>
<p>Это значения из нашего SQLite, а не сохранение Hogwarts Legacy. По умолчанию показан тестовый профиль <code>dashboard_demo</code>.</p>
<label for="profile">ID профиля</label><input id="profile" value="dashboard_demo" maxlength="64" pattern="[A-Za-z0-9_.-]+">
<div class="actions"><button class="secondary" id="read">Загрузить отношения</button></div>
<div id="npcs"></div></div>
<div class="panel full"><h2>Безопасный сюжетный тест</h2>
<p>Здесь создаются только локальные предложения событий. Никакие NPC в Хогвартсе не перемещаются. Сценарий пишется исключительно в <code>dashboard_demo</code>.</p>
<div class="actions"><button id="help">Помочь Себастьяну</button><button class="secondary" id="secret">Рассказать Оминису секрет</button><button class="secondary" id="outbox">Показать очередь событий</button></div>
<pre id="story" aria-live="polite">Предложения появятся здесь.</pre>
</div></section>
<footer>Ключи в браузере не вводятся. Настройка — через <code>setup-free.bat</code>. Диагностика — <code>doctor.bat</code>. Связь с игрой проверяется Ctrl+Alt+F10 только после ручной установки необязательного UE4SS-пробника.</footer>
</main><script>
"use strict";
const el=id=>document.getElementById(id);
async function api(path,body){
 const options={};
 if(body!==undefined){options.method="POST";options.headers={"Content-Type":"application/json"};options.body=JSON.stringify(body);}
 const response=await fetch(path,options);
 const data=await response.json();
 if(!response.ok)throw Error(typeof data.error==="string"?data.error:JSON.stringify(data.error||data));
 return data;
}
async function refresh(){
 try{
  const [h,d]=await Promise.all([api("/health"),api("/v1/diagnostics")]);
  el("version").textContent=h.version;
  el("providers").textContent=(h.configured_providers||[]).join(" + ")||"Ключи ещё не настроены";
  const budget=h.local_free_budget||{};
  el("quotas").textContent=budget.state==="ok"?
    Object.entries(budget.remaining).map(([k,v])=>k+": "+v).join(" · "):
    (budget.state==="locked_corrupt_counter"?"Запросы заблокированы: повреждён счётчик":"Недоступно");
  el("probe").textContent=h.last_probe&&h.last_probe.received_at?
      new Date(h.last_probe.received_at*1000).toLocaleString("ru-RU"):"пока нет";
  el("db").textContent=d.storage_integrity==="ok"?"проверена, цела":String(d.storage_integrity);
 }catch(e){el("version").textContent="Ошибка: "+e.message}
}
function validId(s){return /^[A-Za-z0-9_.-]{1,64}$/.test(s);}
async function relations(){
 const player=el("profile").value.trim();
 if(!validId(player)){el("npcs").textContent="ID: только латинские буквы, цифры, . _ -";return}
 const area=el("npcs");area.replaceChildren();
 for(const [id,name] of [["sebastian","Себастьян"],["ominis","Оминис"],["poppy","Поппи"]]){
  try{
   const data=await api("/v1/world/npc?player_id="+encodeURIComponent(player)+"&npc_id="+id);
   const row=document.createElement("div");row.className="npcrow";
   const title=document.createElement("strong");title.textContent=name;
   const stats=document.createElement("span");stats.className="meters";stats.textContent="Отношение "+data.affinity+" · доверие "+data.trust;
   row.append(title,stats);area.append(row);
  }catch(e){area.textContent="Ошибка: "+e.message;break}
 }
}
async function chat(){
 const btn=el("say");btn.disabled=true;el("reply").textContent="Отправляем…";
 try{
  const r=await api("/v1/chat/completions",{model:"hogwarts-living-world-free",messages:[
   {role:"system",content:"Ты Себастьян из Hogwarts Legacy. Говори по-русски лаконично, без рассказчика, не утверждай, что выполнил игровое действие."},
   {role:"user",content:el("message").value}]});
  el("reply").textContent=r.choices[0].message.content;
 }catch(e){el("reply").textContent="Диалог недоступен: "+e.message}
 finally{btn.disabled=false}
}
async function event(kind){
 try{
  const id="dashboard_"+Date.now()+"_"+Math.floor(Math.random()*1000000);
  const data=await api("/v1/world/event",{player_id:"dashboard_demo",npc_id:"sebastian",event:kind,event_id:id});
  el("story").textContent="Решение учтено: "+kind+"; Себастьян: "+data.affinity+"/доверие "+data.trust+
    ". Это НЕ игровое задание.";
  await relations();
 }catch(e){el("story").textContent="Ошибка: "+e.message}
}
async function proposals(){
 try{const r=await api("/v1/world/outbox?player_id=dashboard_demo");el("story").textContent=JSON.stringify(r.events,null,2)}
 catch(e){el("story").textContent="Ошибка: "+e.message}
}
el("refresh").onclick=refresh;el("read").onclick=relations;el("say").onclick=chat;
el("help").onclick=()=>event("player_helped");el("secret").onclick=()=>event("secret_revealed_to_ominis");
el("outbox").onclick=proposals;
refresh();relations();
</script></body></html>'''
