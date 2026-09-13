let csrf = '';
const hpLang=()=>window.HaushaltProI18n?.language?.()||localStorage.getItem('hp_lang')||'de';
const hpLocale=()=>window.HaushaltProI18n?.locale?.()||(hpLang()==='en'?'en-GB':'de-DE');
const hpT=(key,fallback='',vars={})=>window.HaushaltProI18n?.t?.(key,fallback,vars)??fallback??key;
const hpText=(text)=>window.HaushaltProI18n?.translateText?.(String(text??''))??String(text??'');
const canonicalDeleteConfirmation=value=>String(value??'').trim().toUpperCase()==='DELETE'?'LÖSCHEN':String(value??'').trim();
const hpConfirm=message=>window.confirm(hpText(message));
const hpPrompt=(message,defaultValue)=>window.prompt(hpText(message),defaultValue);
const hpAlert=message=>window.alert(hpText(message));
const formatDateValue=(value,opts={})=>{if(!value)return '–';const raw=String(value);const d=new Date((/^\d{4}-\d{2}-\d{2}$/.test(raw)?raw+'T12:00:00':raw));return Number.isNaN(d.getTime())?raw:d.toLocaleDateString(hpLocale(),opts)};
const formatDateTimeValue=(value)=>{if(!value)return '–';const d=new Date(value);return Number.isNaN(d.getTime())?String(value):new Intl.DateTimeFormat(hpLocale(),{dateStyle:'medium',timeStyle:'medium'}).format(d)};
const formatMonthValue=value=>{const raw=String(value??'');const m=raw.match(/^(\d{4})-(\d{2})$/);if(!m)return raw;const d=new Date(Number(m[1]),Number(m[2])-1,1,12);return new Intl.DateTimeFormat(hpLocale(),{month:'long',year:'numeric'}).format(d)};
const MONTHS_DE=['Januar','Februar','März','April','Mai','Juni','Juli','August','September','Oktober','November','Dezember'];
const MONTHS_EN=['January','February','March','April','May','June','July','August','September','October','November','December'];
const monthNames=()=>hpLang()==='en'?MONTHS_EN:MONTHS_DE;
const nowLocal=new Date();
let selectedMonth=`${nowLocal.getFullYear()}-${String(nowLocal.getMonth()+1).padStart(2,'0')}`;
let accountsCache = [];
let categoriesCache = [];
let payeePresetsCache = [];
let earliestMonth = null;
let txPage = 1;
let txPages = 1;
let currentMe = null;
let runtimeStatus = {registration_enabled:true,public_mode:false,setup_token_required:false};
const viewDataCache=new Map();
function viewCacheGet(key,maxAge=20000){const x=viewDataCache.get(key);return x&&Date.now()-x.time<=maxAge?x.data:null}
function viewCacheSet(key,data){viewDataCache.set(key,{time:Date.now(),data});return data}
function clearViewCache(){viewDataCache.clear()}
async function cachedApi(url,maxAge=20000){const hit=viewCacheGet(url,maxAge);if(hit!==null)return hit;const data=await api(url);return viewCacheSet(url,data)}
const $ = id => document.getElementById(id);
const fmt = v => new Intl.NumberFormat(hpLocale(),{style:'currency',currency:'EUR'}).format(Number(v||0));
const esc = s => String(s ?? '').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));

function updateThemeToggle(){
  const btn=$('themeToggle');if(!btn)return;
  const light=document.documentElement.dataset.theme==='light';
  const label=light?hpT('theme.switchDark',hpLang()==='en'?'🌙 Dark':'🌙 Dunkel'):hpT('theme.switchLight',hpLang()==='en'?'☀ Light':'☀ Hell');
  const title=hpT('theme.switchLabel',hpLang()==='en'?'Switch colour scheme':'Farbschema wechseln');
  btn.textContent=label;btn.title=title;btn.setAttribute('aria-label',title);btn.setAttribute('aria-pressed',light?'true':'false');
}
function applyTheme(mode=localStorage.getItem('hp_theme')||'system'){
  const resolved=mode==='system'?(matchMedia('(prefers-color-scheme: light)').matches?'light':'dark'):mode;
  document.documentElement.dataset.theme=resolved;
  document.documentElement.dataset.themePreference=mode;
  updateThemeToggle();
}
applyTheme();
matchMedia('(prefers-color-scheme: light)').addEventListener?.('change',()=>{if((localStorage.getItem('hp_theme')||'system')==='system')applyTheme('system')});
const topThemeToggle=$('themeToggle');if(topThemeToggle)topThemeToggle.onclick=()=>{
  const next=document.documentElement.dataset.theme==='light'?'dark':'light';
  localStorage.setItem('hp_theme',next);applyTheme(next);
  if($('themeMode'))$('themeMode').value=next;
};
const MONTH_CONTROL_PAIRS=[['dashMonthName','dashYear'],['accountMonthName','accountYear'],['txMonthName','txYear'],['budgetMonthName','budgetYear'],['reportMonthName','reportYear'],['planningMonthName','planningYear']];
function normalizeMonthValue(value,fallback=selectedMonth){const raw=String(value||'');return /^\d{4}-(0[1-9]|1[0-2])$/.test(raw)?raw:fallback}
function setMonthControls(monthId,yearId,value=selectedMonth){
  const safe=normalizeMonthValue(value,`${nowLocal.getFullYear()}-${String(nowLocal.getMonth()+1).padStart(2,'0')}`);
  const [y,m]=safe.split('-').map(Number),sel=$(monthId),year=$(yearId);if(!sel||!year)return safe;
  sel.innerHTML=monthNames().map((n,i)=>`<option value="${i}">${n}</option>`).join('');
  sel.value=String(m-1);year.value=String(y);return safe;
}
function ensureMonthControls(monthId,yearId,fallback=selectedMonth){
  const sel=$(monthId),year=$(yearId);if(!sel||!year)return normalizeMonthValue(fallback);
  const y=Number(year.value),idx=Number(sel.value);
  const valid=sel.options.length===12&&Number.isInteger(idx)&&idx>=0&&idx<=11&&Number.isInteger(y)&&y>=2000&&y<=2100;
  if(valid)return `${y}-${String(idx+1).padStart(2,'0')}`;
  return setMonthControls(monthId,yearId,normalizeMonthValue(fallback));
}
function monthValue(monthId,yearId){return ensureMonthControls(monthId,yearId,selectedMonth)}
function initMonthControls(){MONTH_CONTROL_PAIRS.forEach(([m,y])=>setMonthControls(m,y,selectedMonth));}
async function shiftSelectedMonth(delta){const [y,m]=selectedMonth.split('-').map(Number),d=new Date(y,m-1+delta,1),target=`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`;if(earliestMonth&&target<earliestMonth){toast('Vor dem Start des ersten Kontos gibt es keine Haushaltsdaten.');return}selectedMonth=target;setMonthControls('dashMonthName','dashYear',selectedMonth);await loadDashboard();}
function toast(msg){const e=$('toast');e.textContent=hpText(msg);e.classList.add('show');setTimeout(()=>e.classList.remove('show'),3000)}
async function api(url,opt={}){
  const headers={...(opt.headers||{})};
  if(opt.body && !(opt.body instanceof FormData)) headers['Content-Type']='application/json';
  if(csrf) headers['X-CSRF-Token']=csrf;
  const r=await fetch(url,{credentials:'same-origin',...opt,headers});
  if(r.status===401){showAuth(false,'Sitzung gesperrt. Bitte erneut anmelden.');throw new Error('Nicht angemeldet')}
  if(!r.ok){
    const j=await r.json().catch(()=>({detail:r.statusText}));
    const detail=j?.detail;
    let message=r.statusText||'Fehler';
    if(typeof detail==='string')message=detail;
    else if(Array.isArray(detail))message=detail.map(x=>x?.msg||x?.message||JSON.stringify(x)).join(' · ');
    else if(detail&&typeof detail==='object')message=detail.msg||detail.message||JSON.stringify(detail);
    throw new Error(hpText(message))
  }
  const ct=r.headers.get('content-type')||'';
  const result=ct.includes('application/json')?await r.json():r;
  if((opt.method||'GET').toUpperCase()!=='GET')clearViewCache();
  return result;
}
async function materializeRecurringDue({month=null,year=null}={}){
  const params=new URLSearchParams();
  if(month)params.set('month',month);else if(year)params.set('year',String(year));
  const suffix=params.toString()?'?'+params.toString():'';
  return api('/api/recurring/materialize-due'+suffix,{method:'POST'});
}
async function boot(){
  const st=await fetch('/api/status').then(r=>r.json());runtimeStatus=st;
  if($('appVersion'))$('appVersion').textContent='Version '+(st.version||'–');
  try{const me=await api('/api/me');csrf=me.csrf;showApp(me)}catch{showAuth(!st.initialized)}
}
function showAuth(setup=false,msg=''){
  $('app').hidden=true;$('register').hidden=true;$('auth').hidden=false;
  $('authSubtitle').textContent=setup?'Ersten Benutzer anlegen – ein Passwort genügt.':'Verschlüsseltes Haushaltsbuch';
  $('authSubmit').textContent=setup?'HaushaltPro einrichten':'Anmelden';$('registerBtn').hidden=setup||!runtimeStatus.registration_enabled;$('authForm').dataset.setup=setup?'1':'0';$('authMsg').textContent=msg;
  if($('setupTokenLabel'))$('setupTokenLabel').hidden=!(setup&&runtimeStatus.setup_token_required);
  $('trusted').checked=localStorage.getItem('hp_trusted')==='1';
}
function populateBookSwitcher(me){const sel=$('bookSwitcher');if(!sel)return;sel.innerHTML=(me.books||[]).map(b=>`<option value="${esc(b.id)}" ${me.book?.id===b.id?'selected':''}>${esc(b.name)} · ${b.role==='owner'?'Eigentümer':b.role==='editor'?'Bearbeiter':'Nur Lesen'}</option>`).join('');sel.hidden=(me.books||[]).length<1}
function showApp(me){currentMe=me;$('auth').hidden=true;$('app').hidden=false;$('userLabel').textContent=`${me.username} · ${me.role==='owner'?'Eigentümer':me.role==='editor'?'Bearbeiter':'Nur Lesen'}`;populateBookSwitcher(me);initMonthControls();loadCommon()}
$('authForm').addEventListener('submit',async e=>{
  e.preventDefault();const setup=e.currentTarget.dataset.setup==='1';const username=$('username').value.trim(),password=$('password').value,trusted=$('trusted').checked;
    try{const body={username,password,trusted_device:trusted};if(setup&&runtimeStatus.setup_token_required)body.setup_token=$('setupToken').value;const r=await api(setup?'/api/setup':'/api/login',{method:'POST',body:JSON.stringify(body)});csrf=r.csrf;localStorage.setItem('hp_trusted',trusted?'1':'0');const me=await api('/api/me');showApp(me)}catch(err){$('authMsg').textContent=err.message}
});
function showRegister(){
  $('app').hidden=true;$('auth').hidden=true;$('register').hidden=false;
  $('registerMsg').textContent='';$('registerForm').reset();$('registerUsername').focus();
}
$('registerBtn').onclick=showRegister;
$('registerBack').onclick=()=>showAuth($('authForm').dataset.setup==='1');
$('registerForm').addEventListener('submit',async e=>{
  e.preventDefault();
  const username=$('registerUsername').value.trim(),password=$('registerPassword').value,confirmPassword=$('registerPasswordConfirm').value;
  if(password!==confirmPassword){$('registerMsg').textContent='Die Passwörter stimmen nicht überein.';return}
  if(!username||password.length<10){$('registerMsg').textContent='Benutzername und Passwort mit mindestens 10 Zeichen eingeben.';return}
  try{
    const r=await api('/api/register',{method:'POST',body:JSON.stringify({username,password})});
    $('registerMsg').textContent=r.message||'Benutzer angelegt und wartet auf Freigabe.';
    $('registerPassword').value='';$('registerPasswordConfirm').value='';
  }catch(err){$('registerMsg').textContent=err.message}
});
$('logout').onclick=async()=>{try{await api('/api/logout',{method:'POST'})}finally{csrf='';location.reload()}};
$('bookSwitcher').onchange=async e=>{try{await api('/api/books/'+encodeURIComponent(e.target.value)+'/switch',{method:'POST'});location.reload()}catch(err){toast(err.message)}};
const mobileNavToggle=$('mobileNavToggle'),mainNav=$('mainNav');
function setMobileNav(open){if(!mainNav||!mobileNavToggle)return;mainNav.classList.toggle('mobile-open',!!open);mobileNavToggle.setAttribute('aria-expanded',open?'true':'false');mobileNavToggle.textContent=open?'✕ Schließen':'☰ Menü'}
if(mobileNavToggle)mobileNavToggle.onclick=()=>setMobileNav(!mainNav.classList.contains('mobile-open'));
document.addEventListener('click',e=>{if(window.innerWidth<=800&&mainNav?.classList.contains('mobile-open')&&!mainNav.contains(e.target)&&e.target!==mobileNavToggle)setMobileNav(false)});
document.querySelectorAll('.nav').forEach(b=>b.onclick=()=>{switchView(b.dataset.view);if(window.innerWidth<=800)setMobileNav(false)});
function switchView(name){document.querySelectorAll('.view').forEach(v=>v.hidden=true);$('view-'+name).hidden=false;document.querySelectorAll('.nav').forEach(b=>b.classList.toggle('active',b.dataset.view===name));if(name==='dashboard')reloadDashboardByMode();if(name==='accounts-page')loadAccountManager();if(name==='transactions'){loadTransactions();loadRecurring();}if(name==='budgets')loadBudgets();if(name==='reports')loadReports();if(name==='planning')loadPlanning();if(name==='finance-check')loadFinanceCheck();if(name==='investments')loadInvestments();if(name==='settings')loadSettings()}
async function loadCommon(){const [categories,settings,payees]=await Promise.all([api('/api/categories'),api('/api/settings'),api('/api/payees')]);categoriesCache=categories;payeePresetsCache=payees;$('navInvestments').hidden=settings.investment_tracking!=='true';await materializeRecurringDue();await loadDashboard();const prefetch=()=>{const y=nowLocal.getFullYear(),m=selectedMonth;Promise.allSettled([cachedApi('/api/planning/overview?month='+encodeURIComponent(m),25000),cachedApi('/api/reports/categories?period=month&anchor='+encodeURIComponent(m+'-01'),25000),cachedApi('/api/planning/year?year='+y,30000),cachedApi('/api/dashboard/year?year='+y,30000)])};if('requestIdleCallback' in window)requestIdleCallback(prefetch,{timeout:1200});else setTimeout(prefetch,80)}
function fillAccountSelects(){const options=accountsCache.map(a=>`<option value="${a.id}">${esc(a.name)}</option>`).join('');$('csvAccount').innerHTML=options;$('txAccountFilter').innerHTML='<option value="">Alle Konten</option>'+options}
const accountTypeLabels={checking:'Girokonto',savings:'Sparkonto',cash:'Bargeld',credit_card:'Kreditkarte',paypal:'PayPal'};
const accountTypeLabel=t=>hpText(accountTypeLabels[t]||t);
const DEFAULT_CATEGORY_I18N={Wohnen:'category.default.housing',Lebensmittel:'category.default.groceries',Transport:'category.default.transport',Freizeit:'category.default.leisure',Einkommen:'category.default.income','Sparen & Rücklagen':'category.default.savings'};
const categoryDisplayName=name=>{const value=String(name||'');const key=DEFAULT_CATEGORY_I18N[value];return key?hpT(key,value):hpText(value)};
function renderAccounts(){$('accounts').innerHTML=accountsCache.length?accountsCache.map(a=>`<div class="account-card"><div class="account-head"><span><b>${esc(a.name)}</b><small>${esc(accountTypeLabel(a.type))}</small></span><strong>${fmt(a.balance)}</strong></div><div class="account-month"><span>${hpText('Monatsanfang')} <b>${fmt(a.month_start_balance)}</b></span><span>${hpText('Bis heute')} <b>${fmt(a.balance)}</b></span><span>${hpText('Monatsende')} <b>${fmt(a.month_end_balance)}</b></span></div></div>`).join(''):`<p class="muted">${esc(hpText('Noch keine Konten.'))}</p>`}
function renderDashboardData(d){
  earliestMonth=d.earliest_month||earliestMonth;$('balance').textContent=fmt(d.total_balance);
  const cutoffDate=new Date(d.cutoff+'T12:00:00'),today=nowLocal;
  const cutoffText=cutoffDate.toLocaleDateString(hpLocale());
  const currentMonth=d.cutoff?.slice(0,7)===`${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}`;
  $('balanceHelp').textContent=currentMonth
    ? `Stand bis heute (${cutoffText}). Bei einem anderen Monat wird derselbe Kalendertag wie heute verwendet.`
    : `Stand bis ${cutoffText}. Zum Vergleich wird im ausgewählten Monat derselbe Kalendertag wie heute (${today.getDate()}. Tag) verwendet.`;
  $('balance').closest('.metric').title=`Kontostand zum Vergleichsstichtag ${cutoffText}. Für andere Monate verwendet HaushaltPro denselben Kalendertag wie heute.`;
  $('pending').textContent=fmt(d.pending_outflows);
  $('pending').closest('.metric').title=`Offene Ausgaben vom ${new Date(d.remaining_start+'T12:00:00').toLocaleDateString(hpLocale())} bis ${new Date(d.month_end+'T12:00:00').toLocaleDateString(hpLocale())}`;
  $('monthEnd').textContent=fmt(d.month_end_balance);accountsCache=d.accounts;fillAccountSelects();renderAccounts();renderUpcoming(d.next_payments||[],d);renderAnalysis(d.analysis||{},d);drawChart(d.total_forecast);$('dashPrevMonth').disabled=!!earliestMonth&&selectedMonth<=earliestMonth
}
async function loadDashboard(){
  const monthAtStart=selectedMonth;
  await materializeRecurringDue({month:monthAtStart});
  const url='/api/dashboard?month='+encodeURIComponent(selectedMonth),hit=viewCacheGet(url,20000);
  if(hit)renderDashboardData(hit);
  const d=hit||await cachedApi(url,20000);
  if(selectedMonth===monthAtStart)renderDashboardData(d);
}
function setDashboardMode(){
  const yearly=$('dashPeriod').value==='year';
  $('dashboardMonthHero').hidden=yearly;
  $('dashboardMonthChart').hidden=yearly;
  $('dashboardMonthPanels').hidden=yearly;
  $('dashboardMonthAnalysis').hidden=yearly;
  $('dashboardYearView').hidden=!yearly;
  $('dashMonthName').hidden=yearly;
  $('dashPrevMonth').hidden=yearly;
  $('dashNextMonth').hidden=yearly;
  $('dashToday').textContent=yearly?'Aktuelles Jahr':'Aktueller Monat';
}
function yearSummaryMarkup(months){
  const incomeText=v=>Number(v||0)>0?`+${fmt(v)}`:fmt(0);
  const expenseText=v=>Number(v||0)>0?`−${fmt(v)}`:fmt(0);
  const amountClass=(v,type)=>Number(v||0)>0?`amount ${type}`:'';
  const rows=(months||[]).map(x=>{
    const monthName=monthNames()[Number(x.month.slice(5))-1]||x.month;
    const end=Number(x.month_end_balance||0);
    return `<div class="year-table-row ${end<0?'year-negative':''}">
      <div class="year-month">${esc(monthName)}<small>${esc(x.month.slice(0,4))}</small></div>
      <div class="year-cell" data-label="Plan Einnahmen"><span class="year-value ${amountClass(x.planned_income,'pos')}">${incomeText(x.planned_income)}</span></div>
      <div class="year-cell" data-label="Plan Ausgaben"><span class="year-value ${amountClass(x.planned_expense,'neg')}">${expenseText(x.planned_expense)}</span></div>
      <div class="year-cell" data-label="Plan Sparen"><span class="year-value saving-value">${fmt(x.planned_savings)}</span></div>
      <div class="year-cell" data-label="Ist Einnahmen"><span class="year-value ${amountClass(x.actual_income,'pos')}">${incomeText(x.actual_income)}</span></div>
      <div class="year-cell" data-label="Ist Ausgaben"><span class="year-value ${amountClass(x.actual_expense,'neg')}">${expenseText(x.actual_expense)}</span></div>
      <div class="year-cell year-end" data-label="Monatsende"><strong class="${end<0?'amount neg':''}">${fmt(end)}</strong></div>
    </div>`;
  }).join('');
  return `<div class="year-table" role="table" aria-label="Jahresübersicht">
    <div class="year-table-head" role="row">
      <span>Monat</span><span>Plan Einnahmen</span><span>Plan Ausgaben</span><span>Plan Sparen</span><span>Ist Einnahmen</span><span>Ist Ausgaben</span><span>Monatsende</span>
    </div>${rows}</div>`;
}

async function loadDashboardYear(){
  const year=Number($('dashYear').value)||nowLocal.getFullYear();
  await materializeRecurringDue({year});
  const d=await cachedApi('/api/dashboard/year?year='+year,30000),t=d.totals||{},last=d.months?.at(-1);
  $('dashYearIncome').textContent=fmt(t.actual_income||0);
  $('dashYearExpense').textContent=fmt(t.actual_expense||0);
  $('dashYearSavings').textContent=fmt(t.actual_savings||0);
  $('dashYearEnd').textContent=fmt(last?.month_end_balance||0);
  interactiveMonthlyChart('dashboardYearChart',d.months||[],'month_end_balance','month');
  $('dashboardYearSummary').innerHTML=yearSummaryMarkup(d.months||[]);
}
async function reloadDashboardByMode(){
  setDashboardMode();
  if($('dashPeriod').value==='year')await loadDashboardYear();else await loadDashboard();
}

function renderUpcoming(rows,dashboard){
  if($('upcomingHint')){
    const selectedStart=new Date(dashboard.month_start+'T12:00:00'),selectedEnd=new Date(dashboard.month_end+'T12:00:00'),realToday=new Date();realToday.setHours(0,0,0,0);
    const actualFrom=selectedStart>realToday?selectedStart:new Date(realToday.getTime()+86400000);
    $('upcomingHint').textContent=selectedEnd<realToday?'Dieser Monat liegt in der Vergangenheit.':`Noch kommende Termine in diesem Monat: ${actualFrom.toLocaleDateString(hpLocale())} – ${selectedEnd.toLocaleDateString(hpLocale())}. Maßgeblich ist das echte heutige Datum.`
  }
  $('recurringDash').innerHTML=rows.length?rows.map(r=>`<div class="upcoming-row"><span><b>${r.source==='recurring'?'<span class="recurring-mark" title="Wiederkehrende Buchung" aria-label="Wiederkehrende Buchung">↻</span> ':''}${esc(r.name)}</b><small>${formatDateValue(r.date)} · ${esc(r.account_name)}${r.source==='recurring'?' · wiederkehrend':''}</small></span><strong class="amount ${r.amount<0?'neg':'pos'}">${fmt(r.amount)}</strong></div>`).join(''):'<p class="muted">Keine weiteren Zahlungen in diesem Monat.</p>';
}
function renderAnalysis(a,dashboard){
  if(!$('analysisIncome'))return;
  $('analysisIncome').textContent=fmt(a.booked_income);$('analysisExpense').textContent=fmt(a.booked_expense);$('analysisNet').textContent=fmt(a.balance_to_cutoff);
  $('analysisSavingsRate').textContent=`${Number(a.savings_rate_pct||0).toLocaleString(hpLocale(),{maximumFractionDigits:1})} %`;
  if($('analysisAnnualSavingsRate'))$('analysisAnnualSavingsRate').textContent=`${Number(a.annual_savings_rate_pct||0).toLocaleString(hpLocale(),{maximumFractionDigits:1})} %`;
  if($('analysisAnnualSaved'))$('analysisAnnualSaved').textContent=fmt(a.annual_total_saved);
  if($('analysisAnnualAvgSaved'))$('analysisAnnualAvgSaved').textContent=fmt(a.annual_average_monthly_saved);
  $('analysisDailyIncome').textContent=fmt(a.average_daily_income);$('analysisDailyExpense').textContent=fmt(a.average_daily_expense);$('analysisDailySavings').textContent=fmt(a.average_daily_savings);$('analysisRemainingIncome').textContent=fmt(a.remaining_inflows);
  $('analysisTopCategories').innerHTML=(a.top_expense_categories||[]).length?(a.top_expense_categories||[]).map((x,i)=>`<div class="row analysis-rank"><span><b>${i+1}. ${esc(categoryDisplayName(x.name))}</b></span><strong>${fmt(x.amount)}</strong></div>`).join(''):'<p class="muted">Bis zum Stichtag keine kategorisierten Ausgaben.</p>';
  const months=a.monthly_overview||[];$('analysisMonths').innerHTML=months.slice().reverse().map(m=>{const [y,mo]=m.month.split('-').map(Number);return `<div class="analysis-month-row"><b>${monthNames()[mo-1]} ${y}</b><span class="amount pos">+${fmt(m.income)}</span><span class="amount neg">−${fmt(m.expense)}</span><span class="saving-cell">↗ ${fmt(m.savings||0)}</span><span class="rate-cell">${Number(m.savings_rate_pct||0).toLocaleString(hpLocale(),{maximumFractionDigits:1})} %</span><strong>${fmt(m.net)}</strong></div>`}).join('');drawAnalysisChart(months);
}
function drawAnalysisChart(rows){
  const canvas=$('analysisChart');if(!canvas)return;const ctx=canvas.getContext('2d'),ratio=devicePixelRatio||1,w=Math.max(320,canvas.clientWidth)*ratio,h=Math.max(190,canvas.clientHeight||220)*ratio;if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h}ctx.clearRect(0,0,w,h);if(!rows.length)return;
  const vals=rows.flatMap(r=>[Number(r.income||0),Number(r.expense||0),Number(r.savings||0)]),max=Math.max(1,...vals),left=48*ratio,right=12*ratio,top=14*ratio,bottom=38*ratio,pw=w-left-right,ph=h-top-bottom,group=pw/rows.length,bar=Math.max(3,group*.28),css=getComputedStyle(document.documentElement),grid=css.getPropertyValue('--line').trim(),text=css.getPropertyValue('--muted').trim(),accent=css.getPropertyValue('--accent').trim();
  ctx.font=`${9*ratio}px system-ui`;ctx.textAlign='right';ctx.textBaseline='middle';for(let i=0;i<4;i++){const v=max*(3-i)/3,y=top+ph*i/3;ctx.strokeStyle=grid;ctx.lineWidth=ratio;ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(w-right,y);ctx.stroke();ctx.fillStyle=text;ctx.fillText(new Intl.NumberFormat(hpLocale(),{notation:'compact',maximumFractionDigits:1}).format(v),left-6*ratio,y)}
  rows.forEach((r,i)=>{const cx=left+group*(i+.5),hi=Number(r.income||0)/max*ph,he=Number(r.expense||0)/max*ph,hs=Number(r.savings||0)/max*ph,bw=Math.max(2,bar*.72);ctx.fillStyle=accent;ctx.fillRect(cx-bw*1.65,top+ph-hi,bw,hi);ctx.fillStyle='#ff9c9c';ctx.fillRect(cx-bw*.5,top+ph-he,bw,he);ctx.fillStyle='#7db7ff';ctx.fillRect(cx+bw*.65,top+ph-hs,bw,hs);if(i%2===0||rows.length<=8){const [y,m]=r.month.split('-');ctx.fillStyle=text;ctx.font=`${8*ratio}px system-ui`;ctx.textAlign='center';ctx.textBaseline='top';ctx.fillText(`${m}/${String(y).slice(2)}`,cx,h-bottom+8*ratio)}});
}
function drawChart(points){
  const canvas=$('chart'),ctx=canvas.getContext('2d'),ratio=devicePixelRatio||1,state={hover:null};
  function paint(){
    const w=Math.max(320,canvas.clientWidth)*ratio,h=Math.max(220,canvas.clientHeight)*ratio;if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h}
    ctx.clearRect(0,0,w,h);if(!points.length)return;
    const vals=points.flatMap((p,i)=>i===0&&p.opening_balance!=null?[Number(p.opening_balance),Number(p.balance)]:[Number(p.balance)]),min0=Math.min(...vals),max0=Math.max(...vals),extra=Math.max(1,(max0-min0)*.08),min=min0-extra,max=max0+extra,span=max-min||1;
    const left=74*ratio,right=20*ratio,top=18*ratio,bottom=46*ratio,plotW=w-left-right,plotH=h-top-bottom,xFor=i=>left+(points.length===1?0:plotW*i/(points.length-1)),yFor=v=>top+(max-v)/span*plotH;
    const css=getComputedStyle(document.documentElement),grid=css.getPropertyValue('--line').trim(),text=css.getPropertyValue('--muted').trim(),accent=css.getPropertyValue('--accent').trim();
    ctx.font=`${10*ratio}px system-ui`;ctx.textAlign='right';ctx.textBaseline='middle';
    for(let i=0;i<5;i++){const value=max-span*i/4,y=top+plotH*i/4;ctx.strokeStyle=grid;ctx.lineWidth=ratio;ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(w-right,y);ctx.stroke();ctx.fillStyle=text;ctx.fillText(new Intl.NumberFormat(hpLocale(),{style:'currency',currency:'EUR',maximumFractionDigits:0}).format(value),left-8*ratio,y)}
    // Every day of the selected month is shown on the X axis: 1..28/29/30/31.
    ctx.textAlign='center';ctx.textBaseline='top';ctx.fillStyle=text;ctx.font=`${Math.max(7,Math.min(10,plotW/points.length/ratio*.7))*ratio}px system-ui`;
    points.forEach((p,i)=>ctx.fillText(String(new Date(p.date+'T12:00:00').getDate()),xFor(i),h-bottom+10*ratio));
    ctx.strokeStyle=accent;ctx.lineWidth=2.5*ratio;ctx.beginPath();points.forEach((p,i)=>{const x=xFor(i),y=yFor(Number(p.balance));if(i===0){const opening=p.opening_balance!=null?Number(p.opening_balance):Number(p.balance);ctx.moveTo(x,yFor(opening));ctx.lineTo(x,y)}else{ctx.lineTo(x,y)}});ctx.stroke();
    if(state.hover!==null){const i=state.hover,p=points[i],x=xFor(i),v=Number(p.balance),y=yFor(v);ctx.save();ctx.setLineDash([5*ratio,4*ratio]);ctx.strokeStyle=text;ctx.lineWidth=ratio;ctx.beginPath();ctx.moveTo(x,top);ctx.lineTo(x,h-bottom);ctx.moveTo(left,y);ctx.lineTo(w-right,y);ctx.stroke();ctx.restore();ctx.fillStyle=accent;ctx.beginPath();ctx.arc(x,y,4*ratio,0,Math.PI*2);ctx.fill();ctx.fillStyle=text;ctx.textAlign='right';ctx.textBaseline='middle';ctx.font=`${11*ratio}px system-ui`;ctx.fillText(fmt(v),left-8*ratio,y);const label=`${new Date(p.date+'T12:00:00').toLocaleDateString(hpLocale())} · ${fmt(v)}`;ctx.font=`${12*ratio}px system-ui`;const tw=ctx.measureText(label).width+18*ratio,th=28*ratio,tx=Math.min(Math.max(left,x-tw/2),w-right-tw),ty=Math.max(top,y-38*ratio);ctx.fillStyle='rgba(20,24,30,.92)';ctx.fillRect(tx,ty,tw,th);ctx.fillStyle='#fff';ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(label,tx+tw/2,ty+th/2)}
  }
  const hoverAt=clientX=>{const rect=canvas.getBoundingClientRect(),x=(clientX-rect.left)*(canvas.width/rect.width),left=74*ratio,right=20*ratio,plotW=canvas.width-left-right;state.hover=Math.max(0,Math.min(points.length-1,Math.round((x-left)/plotW*(points.length-1))));paint()};
  canvas.onmousemove=e=>hoverAt(e.clientX);canvas.onmouseleave=()=>{state.hover=null;paint()};canvas.ontouchmove=e=>{if(e.touches[0])hoverAt(e.touches[0].clientX)};paint();
}
async function selectDashboardMonth(){selectedMonth=monthValue('dashMonthName','dashYear');if(earliestMonth&&selectedMonth<earliestMonth){selectedMonth=earliestMonth;setMonthControls('dashMonthName','dashYear',selectedMonth);toast('Ansicht beginnt mit dem ersten Konto.')}await loadDashboard()}
$('dashMonthName').onchange=selectDashboardMonth;$('dashYear').onchange=selectDashboardMonth;
$('dashPrevMonth').onclick=()=>shiftSelectedMonth(-1);$('dashNextMonth').onclick=()=>shiftSelectedMonth(1);$('dashPeriod').onchange=reloadDashboardByMode;$('dashYear').onchange=async()=>{if($('dashPeriod').value==='year')await loadDashboardYear();else await selectDashboardMonth()};$('dashToday').onclick=async()=>{selectedMonth=`${nowLocal.getFullYear()}-${String(nowLocal.getMonth()+1).padStart(2,'0')}`;setMonthControls('dashMonthName','dashYear',selectedMonth);$('dashYear').value=nowLocal.getFullYear();await reloadDashboardByMode()};
function openModal(html,onSave){$('modalContent').innerHTML=html;$('modalForm').reset();modal.showModal();$('modalCancel').onclick=()=>modal.close();$('modalForm').onsubmit=async e=>{e.preventDefault();try{await onSave(new FormData(e.currentTarget));modal.close();await loadCommon();toast('Gespeichert')}catch(err){toast(err.message)}}}
function accountOptions(selected=''){return accountsCache.map(a=>`<option value="${a.id}" ${String(a.id)===String(selected)?'selected':''}>${esc(a.name)}</option>`).join('')}
function categoryTypeLabel(t){return hpText(t==='income'?'Einnahme':t==='savings'?'Sparen':'Ausgabe')}
function categoryOptions(selected=''){return `<option value="">${esc(hpText('Kategorie wählen …'))}</option>`+categoriesCache.map(c=>`<option value="${c.id}" ${String(c.id)===String(selected)?'selected':''}>${esc(categoryDisplayName(c.name))} · ${esc(categoryTypeLabel(c.direction))}</option>`).join('')}
function accountDialog(account=null){const today=new Date().toISOString().slice(0,10);const typeOpts=Object.entries(accountTypeLabels).map(([k,v])=>`<option value="${k}" ${account?.type===k?'selected':''}>${esc(hpText(v))}</option>`).join('');openModal(`<h2>${account?'Konto bearbeiten':'Konto anlegen'}</h2><label>Name<input name="name" required value="${esc(account?.name||'')}"></label><label>Typ<select name="type">${typeOpts}</select></label><label>Ab wann zählt das Konto?<input name="start_date" type="date" required value="${account?.start_date||today}"><small>Der Startsaldo gilt unmittelbar vor den Buchungen dieses Tages.</small></label><label>IBAN<input name="iban" autocomplete="off" autocapitalize="characters" spellcheck="false" value="${esc(account?.iban||'')}"></label><label>Startsaldo EUR<input name="opening_balance" type="number" step="0.01" value="${account?.opening_balance??0}"></label>`,async f=>{const body={name:f.get('name'),type:f.get('type'),iban:f.get('iban')||null,opening_balance:String(f.get('opening_balance')),start_date:f.get('start_date')};await api(account?'/api/accounts/'+account.id:'/api/accounts',{method:account?'PUT':'POST',body:JSON.stringify(body)});if(!account&&body.start_date){setMonthControls('accountMonthName','accountYear',body.start_date.slice(0,7))}if(document.querySelector('.nav.active')?.dataset.view==='accounts-page')await loadAccountManager()})}

$('quickAccount').onclick=()=>accountDialog();$('newAccount').onclick=()=>accountDialog();
function txDialog(tx=null,forceRecurring=false){
  if(!accountsCache.length)return toast('Zuerst ein Konto anlegen.');
  const isRecurring=!!tx?.recurring||forceRecurring;
  const freq=tx?.recurring_frequency||'monthly';
  const recurringBlock=`<label class="check recurring-check"><input id="txRecurring" name="recurring" type="checkbox" ${isRecurring?'checked':''}> Wiederkehrende Zahlung / Einnahme</label>
    <div id="txRecurringFields" class="subform" ${isRecurring?'':'hidden'}>
      <label>Intervall<select name="recurring_frequency"><option value="monthly" ${freq==='monthly'?'selected':''}>Monatlich</option><option value="weekly" ${freq==='weekly'?'selected':''}>Wöchentlich</option><option value="yearly" ${freq==='yearly'?'selected':''}>Jährlich</option><option value="daily" ${freq==='daily'?'selected':''}>Täglich</option></select></label>
      <label>Enddatum (optional)<input name="recurring_until" type="date" value="${esc(tx?.recurring_until||'')}"><small>Leer lassen für unbegrenzt.</small></label>
      ${tx?.recurring?`<label>Serienänderung gültig ab<input name="recurring_effective_from" type="date" required value="${new Date().toISOString().slice(0,10)}"><small>Nur die Serie wird ab diesem Datum geändert. Frühere Monate bleiben unverändert.</small></label>`:''}
      <small class="info-note">Die Wiederholung wird für alle Folgemonate in Prognose und Chart berechnet. Die erste Buchung wird nicht doppelt gezählt.</small>
    </div>`;
  openModal(`<h2>${tx?'Buchung bearbeiten':'Buchung anlegen'}</h2><label>Konto<select name="account_id">${accountOptions(tx?.account_id)}</select></label><label>Name der Buchung<input name="name" maxlength="160" required placeholder="z. B. KFZ-Versicherung" value="${esc(tx?.name||tx?.recurring_name||tx?.payee||'')}"><small>Dieser Name dient zur eindeutigen Dokumentation und Suche.</small></label><label>Betrag EUR<input name="amount" type="number" min="0" step="0.01" required value="${tx?Math.abs(tx.amount):''}"></label><label>Datum<input name="booking_date" type="date" required value="${tx?.booking_date||new Date().toISOString().slice(0,10)}"><small>Liegt das Datum in der Zukunft, erscheint die Buchung ab diesem Tag in der Vorschau.</small></label><label>Empfänger<input name="payee" list="payeeSuggestions" autocomplete="off" placeholder="z. B. REWE, ALDI, Allianz" value="${esc(tx?.payee||'')}"><datalist id="payeeSuggestions">${payeePresetsCache.map(p=>`<option value="${esc(p.name)}"></option>`).join('')}</datalist></label><label class="check remember-payee"><input name="remember_payee" type="checkbox"> Empfänger für spätere Vorauswahl merken</label><small class="muted optin-note">Nur mit diesem Häkchen wird der Empfänger in der bearbeitbaren Vorschlagsliste gespeichert.</small><label>Kategorie<select name="category_id" required>${categoryOptions(tx?.category_id)}</select><small>Die Kategorie bestimmt automatisch, ob die Buchung Einnahme, Ausgabe oder Sparen ist.</small></label>${recurringBlock}<label>Prognose-Sicherheit<select name="confidence"><option value="fixed" ${!tx||tx?.confidence==='fixed'?'selected':''}>Fest</option><option value="likely" ${tx?.confidence==='likely'?'selected':''}>Wahrscheinlich</option><option value="estimated" ${tx?.confidence==='estimated'?'selected':''}>Geschätzt</option></select><small>Relevant für zukünftige Prognosen.</small></label><label class="check"><input name="fixed_cost" type="checkbox" ${tx?.fixed_cost?'checked':''}> Fixkosten / vertraglich gebunden</label><label>Tags (kommagetrennt)<input name="tags" value="${esc((tx?.tags||[]).join(', '))}"></label><label>Notiz<input name="note" value="${esc(tx?.note||'')}"></label>`,async f=>{
    const recurring=f.get('recurring')==='on';
    const body={account_id:Number(f.get('account_id')),amount:String(f.get('amount')),direction:null,booking_date:f.get('booking_date'),name:f.get('name')||null,payee:f.get('payee')||null,note:f.get('note')||null,category_id:f.get('category_id')?Number(f.get('category_id')):null,status:'executed',tags:String(f.get('tags')||'').split(',').map(x=>x.trim()).filter(Boolean),splits:[],recurring,recurring_frequency:recurring?f.get('recurring_frequency'):null,recurring_until:recurring&&f.get('recurring_until')?f.get('recurring_until'):null,recurring_effective_from:recurring&&f.get('recurring_effective_from')?f.get('recurring_effective_from'):null,confidence:f.get('confidence')||'fixed',fixed_cost:f.get('fixed_cost')==='on',remember_payee:f.get('remember_payee')==='on'};
    await api(tx?'/api/transactions/'+tx.id:'/api/transactions',{method:tx?'PUT':'POST',body:JSON.stringify(body)});
    await loadTransactions();await loadRecurring();
  });
  const cb=$('txRecurring'),fields=$('txRecurringFields');
  if(cb){cb.onchange=()=>{if(tx?.recurring&&!cb.checked){toast('Eine bestehende Serie beendest oder löschst du unten bei „Wiederkehrende Buchungen“.');cb.checked=true;return}fields.hidden=!cb.checked}}
}
async function transferDialog(transferId=null){
  if(accountsCache.length<2)return toast('Für einen Transfer werden mindestens zwei aktive Konten benötigt.');
  let tr=null;if(transferId)tr=await api('/api/transfers/'+transferId);
  const today=new Date().toISOString().slice(0,10),from=tr?.from_account_id||accountsCache[0]?.id,to=tr?.to_account_id||accountsCache.find(a=>a.id!==from)?.id;
  openModal(`<h2>${tr?'Transfer bearbeiten':'Transfer anlegen'}</h2><p class="muted">Interne Umbuchung zwischen deinen eigenen Konten. Sie verändert die Kontostände, zählt aber nicht als Einnahme oder Ausgabe des Haushalts.</p><label>Von Konto<select name="from_account_id">${accountOptions(from)}</select></label><label>Auf Konto<select name="to_account_id">${accountOptions(to)}</select></label><label>Betrag EUR<input name="amount" type="number" min="0.01" step="0.01" required value="${tr?Number(tr.amount).toFixed(2):''}"></label><label>Datum<input name="booking_date" type="date" required value="${tr?.booking_date||today}"></label><label>Name<input name="name" maxlength="160" required value="${esc(tr?.name||'Interner Transfer')}"></label><label>Notiz<input name="note" value="${esc(tr?.note||'')}"></label>`,async f=>{
    const body={from_account_id:Number(f.get('from_account_id')),to_account_id:Number(f.get('to_account_id')),amount:String(f.get('amount')),booking_date:f.get('booking_date'),name:f.get('name')||'Interner Transfer',note:f.get('note')||null};
    if(body.from_account_id===body.to_account_id)throw new Error('Quell- und Zielkonto müssen verschieden sein.');
    await api(tr?'/api/transfers/'+tr.id:'/api/transfers',{method:tr?'PUT':'POST',body:JSON.stringify(body)});await loadTransactions();await loadDashboard();
  });
}
$('quickTx').onclick=()=>txDialog();$('newTx').onclick=()=>txDialog();$('newTransfer').onclick=()=>transferDialog();$('newRecurringTx').onclick=()=>recDialog(null);
async function loadAccountManager(){const month=ensureMonthControls('accountMonthName','accountYear',selectedMonth);const rows=await api('/api/accounts?month='+encodeURIComponent(month));accountsCache=rows;fillAccountSelects();$('accountManager').innerHTML=rows.length?rows.map(a=>`<article class="panel account-manage-card"><div class="account-head"><span><b>${esc(a.name)}</b><small>${esc(accountTypeLabel(a.type))} · ${esc(hpText('Start'))} ${formatDateValue(a.start_date)}</small></span><strong>${fmt(a.balance)}</strong></div><div class="account-month"><span>Monatsanfang <b>${fmt(a.month_start_balance)}</b></span><span>Bis Stichtag <b>${fmt(a.balance)}</b></span><span>Monatsende <b>${fmt(a.month_end_balance)}</b></span></div><div class="account-actions"><button data-aedit="${a.id}">Kontodaten bearbeiten</button><button class="ghost" data-acorrect="${a.id}">Monatsanfang korrigieren</button><button class="ghost" data-areconcile="${a.id}">Kontostand abgleichen</button></div></article>`).join(''):'<article class="panel"><p class="muted">Für diesen Monat gibt es noch kein aktives Konto.</p></article>';document.querySelectorAll('[data-aedit]').forEach(b=>b.onclick=()=>accountDialog(rows.find(a=>a.id===Number(b.dataset.aedit))));document.querySelectorAll('[data-acorrect]').forEach(b=>b.onclick=()=>accountCorrectionDialog(rows.find(a=>a.id===Number(b.dataset.acorrect)),month));document.querySelectorAll('[data-areconcile]').forEach(b=>b.onclick=()=>accountReconcileDialog(rows.find(a=>a.id===Number(b.dataset.areconcile))))}
async function accountCorrectionDialog(account,month){
  const corrections=await api('/api/accounts/'+account.id+'/corrections');
  const rows=corrections.map(c=>`<div class="correction-row"><span><b>${monthNames()[Number(c.month.slice(5,7))-1]} ${c.month.slice(0,4)}</b><small>${c.note?esc(c.note):'Manuelle Monatskorrektur'}</small></span><span><strong>${fmt(c.opening_balance)}</strong> <button type="button" class="ghost danger-outline" data-cdel="${esc(c.month)}">Löschen</button></span></div>`).join('')||'<p class="muted">Noch keine Monatskorrekturen.</p>';
  openModal(`<h2>Monatsanfang korrigieren</h2><p class="muted">${esc(account.name)}</p><label>Monat<input name="month" type="month" required value="${month}"></label><label>Monatsanfang EUR<input name="opening_balance" type="number" step="0.01" required value="${Number(account.month_start_balance).toFixed(2)}"></label><label>Notiz<input name="note" placeholder="z. B. Abgleich mit Kontoauszug"></label><small>Du kannst jeden Monat ab Kontostart korrigieren. Dieser Wert ersetzt nur den Monatsanfang; vorhandene Buchungen bleiben unverändert.</small><div class="correction-list"><h3>Gespeicherte Monatskorrekturen</h3>${rows}</div>`,async f=>{const target=f.get('month');if(target<account.start_date.slice(0,7))throw new Error('Der Korrekturmonat liegt vor dem Kontostart.');await api('/api/accounts/'+account.id+'/month-opening',{method:'PUT',body:JSON.stringify({month:target,opening_balance:String(f.get('opening_balance')),note:f.get('note')||null})});setMonthControls('accountMonthName','accountYear',target);await loadAccountManager();selectedMonth=target;setMonthControls('dashMonthName','dashYear',target);await loadDashboard()});
  document.querySelectorAll('[data-cdel]').forEach(b=>b.onclick=async()=>{if(hpConfirm('Monatskorrektur für '+b.dataset.cdel+' löschen?')){await api('/api/accounts/'+account.id+'/month-opening/'+encodeURIComponent(b.dataset.cdel),{method:'DELETE'});modal.close();await loadAccountManager();await loadDashboard();toast('Monatskorrektur gelöscht')}})
}
$('accountReload').onclick=loadAccountManager;$('accountMonthName').onchange=loadAccountManager;$('accountYear').onchange=loadAccountManager;


async function attachmentDialog(txId){
  const rows=await api('/api/transactions/'+txId+'/attachments');
  openModal(`<h2>Belege / Anhänge</h2><p class="muted">PDF oder Bild direkt verschlüsselt in der SQLCipher-Datenbank speichern.</p><input id="attachmentFile" type="file" accept=".pdf,image/jpeg,image/png,image/webp,text/plain"><button id="attachmentUpload" type="button">Beleg hochladen</button><div class="correction-list">${rows.map(x=>`<div class="row"><span><b>${esc(x.filename)}</b><small>${Math.round(x.size/1024)} KB</small></span><span><button type="button" class="ghost" data-adownload="${x.id}">Öffnen</button><button type="button" class="ghost danger-outline" data-adel="${x.id}">Löschen</button></span></div>`).join('')||'<p class="muted">Noch keine Belege.</p>'}</div>`,async()=>{});
  $('modalSave').hidden=true;
  $('attachmentUpload').onclick=async()=>{const file=$('attachmentFile').files[0];if(!file)return toast('Datei wählen');const f=new FormData();f.append('file',file);await api('/api/transactions/'+txId+'/attachments',{method:'POST',body:f});modal.close();attachmentDialog(txId)};
  document.querySelectorAll('[data-adownload]').forEach(b=>b.onclick=async()=>{const r=await api('/api/attachments/'+b.dataset.adownload);const blob=await r.blob(),u=URL.createObjectURL(blob),a=document.createElement('a');a.href=u;a.download='beleg';a.click();URL.revokeObjectURL(u)});
  document.querySelectorAll('[data-adel]').forEach(b=>b.onclick=async()=>{if(hpConfirm('Beleg löschen?')){await api('/api/attachments/'+b.dataset.adel,{method:'DELETE'});modal.close();attachmentDialog(txId)}})
}
function updateTransactionPeriodControls(){
  const period=$('txPeriod').value;
  $('txMonthName').hidden=period!=='month';
  $('txYear').hidden=period==='all';
}
function bindTransactionRows(rows){
  document.querySelectorAll('[data-edit]').forEach(b=>{const row=rows.find(x=>x.id===Number(b.dataset.edit));b.onclick=()=>row?.transfer?transferDialog(row.transfer_id):row?.recurring?recurringTransactionOverrideDialog(row):txDialog(row)});
  document.querySelectorAll('[data-cancel]').forEach(b=>{const row=rows.find(x=>x.id===Number(b.dataset.cancel));b.onclick=async()=>{if(row?.transfer){if(hpConfirm('Gesamten Transfer auf beiden Konten stornieren?'))await api('/api/transfers/'+row.transfer_id,{method:'DELETE'})}else if(hpConfirm('Buchung stornieren? Sie wird aus der normalen Liste ausgeblendet, bleibt aber in der Historie erhalten.'))await api('/api/transactions/'+b.dataset.cancel,{method:'DELETE'});await loadTransactions();await loadDashboard()}});
  document.querySelectorAll('[data-attach]').forEach(b=>b.onclick=()=>attachmentDialog(Number(b.dataset.attach)));
  document.querySelectorAll('[data-delete]').forEach(b=>{const row=rows.find(x=>x.id===Number(b.dataset.delete));b.onclick=async()=>{if(row?.transfer){if(hpConfirm('Transfer auf beiden Konten endgültig löschen?'))await api('/api/transfers/'+row.transfer_id+'?hard=true',{method:'DELETE'})}else if(hpConfirm('Buchung endgültig löschen? Eine verknüpfte Wiederholungsserie bleibt bestehen und kann darunter separat gelöscht werden.'))await api('/api/transactions/'+b.dataset.delete+'?hard=true',{method:'DELETE'});await loadTransactions();await loadRecurring();await loadDashboard()}});
}
async function loadTransactions(resetPage=false){
  if(resetPage)txPage=1;
  updateTransactionPeriodControls();
  const aid=$('txAccountFilter').value,q=$('txSearch').value.trim(),period=$('txPeriod').value;
  const month=monthValue('txMonthName','txYear'),year=Number($('txYear').value)||nowLocal.getFullYear(),pageSize=$('txPageSize').value==='0'?0:(Number($('txPageSize').value)||25);
  if(period==='month')await materializeRecurringDue({month});
  else if(period==='year')await materializeRecurringDue({year});
  else await materializeRecurringDue({month:`${nowLocal.getFullYear()}-${String(nowLocal.getMonth()+1).padStart(2,'0')}`});
  let url=`/api/transactions/paged?period=${encodeURIComponent(period)}&page=${txPage}&page_size=${pageSize}`;
  if(period==='month')url+='&month='+encodeURIComponent(month);
  if(period==='year')url+='&year='+encodeURIComponent(year);
  if(aid)url+='&account_id='+encodeURIComponent(aid);
  if(q)url+='&q='+encodeURIComponent(q);
  const data=await api(url),rows=data.items||[];
  txPage=data.page||1;txPages=data.pages||1;
  $('txBody').innerHTML=rows.map(t=>`<tr><td>${esc(formatDateValue(t.booking_date))}</td><td><b>${esc(t.name||t.recurring_name||'Buchung')}</b>${t.tags?.length?`<small class="table-sub">${t.tags.map(esc).join(' · ')}</small>`:''}</td><td>${esc(t.account_name)}</td><td>${esc(t.transfer?(t.transfer_side==='out'?t.transfer_to_account_name:t.transfer_from_account_name):(t.payee||'—'))}</td><td>${t.transfer?'<span class="muted">Interner Transfer</span>':esc(t.category_name?categoryDisplayName(t.category_name):'—')}</td><td>${t.transfer?`<span class="badge transfer-badge">↔ Transfer ${t.transfer_side==='out'?'Ausgang':'Eingang'}</span>`:(t.recurring?`<span class="badge"><span class="recurring-mark">↻</span>${esc(hpT('recurring.label','Wiederkehrend'))} · ${esc(hpText(({monthly:'Monatlich',weekly:'Wöchentlich',yearly:'Jährlich',daily:'Täglich'})[t.recurring_frequency]||t.recurring_frequency))} · ${esc(t.status==='planned'?hpT('recurring.planned','Geplant'):hpT('recurring.executed','Gebucht'))}</span>`:'—')}</td><td class="right amount ${t.amount<0?'neg':'pos'}">${fmt(t.amount)}</td><td class="actions"><button data-edit="${t.id}">${esc(t.recurring?hpText('Termin anpassen'):hpText('Bearbeiten'))}</button><button class="ghost" data-cancel="${t.id}">Storno</button><button class="ghost" data-attach="${t.id}">Belege</button><button class="ghost" data-delete="${t.id}">Löschen</button></td></tr>`).join('')||'<tr><td colspan="8">Keine Buchungen.</td></tr>';
  $('txPageInfo').textContent=`Seite ${txPage} / ${txPages} · ${data.total||0} Einträge`;
  $('txFirst').disabled=$('txPrev').disabled=txPage<=1;
  $('txNext').disabled=$('txLast').disabled=txPage>=txPages;
  bindTransactionRows(rows);
}
$('txReload').onclick=()=>loadTransactions(true);
$('txPeriod').onchange=()=>loadTransactions(true);
$('txMonthName').onchange=()=>loadTransactions(true);
$('txYear').onchange=()=>loadTransactions(true);
$('txSearch').onkeydown=e=>{if(e.key==='Enter')loadTransactions(true)};
$('txAccountFilter').onchange=()=>loadTransactions(true);
$('txPageSize').onchange=()=>loadTransactions(true);
$('txFirst').onclick=()=>{txPage=1;loadTransactions()};
$('txPrev').onclick=()=>{txPage=Math.max(1,txPage-1);loadTransactions()};
$('txNext').onclick=()=>{txPage=Math.min(txPages,txPage+1);loadTransactions()};
$('txLast').onclick=()=>{txPage=txPages;loadTransactions()};
function setTransactionTab(tab){const recurring=tab==='recurring';$('txAllView').hidden=recurring;$('txRecurringView').hidden=!recurring;$('txTabAll').classList.toggle('active',!recurring);$('txTabRecurring').classList.toggle('active',recurring);$('txTabAll').setAttribute('aria-selected',String(!recurring));$('txTabRecurring').setAttribute('aria-selected',String(recurring));if(recurring)loadRecurring();else loadTransactions()}
$('txTabAll').onclick=()=>setTransactionTab('all');$('txTabRecurring').onclick=()=>setTransactionTab('recurring');

function recDialog(rec=null){
  if(!accountsCache.length)return toast('Zuerst ein Konto anlegen.');
  const today=new Date().toISOString().slice(0,10),next=rec?.next_date||today;
  openModal(`<h2>Wiederholungsserie bearbeiten</h2><p class="muted">Die Serie ist die Vertragsvorlage. Beim Speichern werden alle bekannten zukünftigen Termine sofort als geplante Buchungen angelegt. Änderungen können ab einem Stichtag gelten, ohne bereits ausgeführte Historie umzuschreiben.</p><label>Konto<select name="account_id">${accountOptions(rec?.account_id)}</select></label><label>Name<input name="name" required value="${esc(rec?.name||'')}"></label><label>Kategorie<select name="category_id">${categoryOptions(rec?.category_id)}</select></label><label>Betrag EUR<input name="amount" type="number" min="0" step="0.01" required value="${rec?Math.abs(rec.amount):''}"></label><label>Nächster offener Termin<input name="next_date" type="date" required value="${next}"></label>${rec?`<label>Änderung gültig ab<input name="effective_from" type="date" required value="${today}"><small>Ab diesem Datum gilt die neue Serienversion. Frühere Monate bleiben unverändert.</small></label>`:''}<label>Intervall<select name="frequency"><option value="monthly" ${rec?.frequency==='monthly'?'selected':''}>Monatlich</option><option value="weekly" ${rec?.frequency==='weekly'?'selected':''}>Wöchentlich</option><option value="yearly" ${rec?.frequency==='yearly'?'selected':''}>Jährlich</option><option value="daily" ${rec?.frequency==='daily'?'selected':''}>Täglich</option></select></label><label>Enddatum (optional)<input name="valid_until" type="date" value="${esc(rec?.valid_until||'')}"><small>Leer lassen für unbegrenzt.</small></label><label>Prognose-Sicherheit<select name="confidence"><option value="fixed" ${!rec||rec?.confidence==='fixed'?'selected':''}>Fest</option><option value="likely" ${rec?.confidence==='likely'?'selected':''}>Wahrscheinlich</option><option value="estimated" ${rec?.confidence==='estimated'?'selected':''}>Geschätzt</option></select><small>Steuert konservative/optimistische Prognosen.</small></label><label class="check"><input name="fixed_cost" type="checkbox" ${rec?.fixed_cost?'checked':''}> Fixkosten / vertraglich gebunden</label><label>Maximallimit EUR<input name="max_amount" type="number" min="0" step="0.01" value="${rec?.max_amount??''}"></label>`,async f=>{const body={account_id:Number(f.get('account_id')),category_id:f.get('category_id')?Number(f.get('category_id')):null,name:f.get('name'),amount:String(f.get('amount')),next_date:f.get('next_date'),frequency:f.get('frequency'),kind:'direct_debit',max_amount:f.get('max_amount')?String(f.get('max_amount')):null,active:true,valid_until:f.get('valid_until')||null,confidence:f.get('confidence')||'fixed',fixed_cost:f.get('fixed_cost')==='on'};if(rec)body.effective_from=f.get('effective_from');await api(rec?'/api/recurring/'+rec.id:'/api/recurring',{method:rec?'PUT':'POST',body:JSON.stringify(body)});await loadRecurring();await loadTransactions();await loadDashboard()})
}
function recurringOverrideDialog(rec){
  const activeMonth=$('txPeriod')?.value==='month'?monthValue('txMonthName','txYear'):selectedMonth;
  const [y,m]=activeMonth.split('-').map(Number);
  const plannedDay=Number((rec.next_date||'').slice(8,10))||1;
  const lastDay=new Date(y,m,0).getDate();
  const due=`${y}-${String(m).padStart(2,'0')}-${String(Math.min(plannedDay,lastDay)).padStart(2,'0')}`;
  openModal(`<h2>Monatsbetrag anpassen</h2><p class="muted">${esc(rec.name)} · nur dieser Termin wird geändert. Die wiederkehrende Planung selbst bleibt unverändert.</p><label>Termin<input name="due_date" type="date" required value="${due}"></label><label>Betrag EUR<input name="amount" type="number" min="0" step="0.01" required value="${Math.abs(Number(rec.amount)).toFixed(2)}"></label><label>Notiz<input name="note" placeholder="z. B. tatsächliches Gehalt in diesem Monat"></label><small>Im nächsten Monat gilt automatisch wieder der normale Serienbetrag, sofern du dort keinen eigenen Monatsbetrag hinterlegst.</small>`,async f=>{await api('/api/recurring/'+rec.id+'/override',{method:'PUT',body:JSON.stringify({due_date:f.get('due_date'),amount:String(f.get('amount')),note:f.get('note')||null})});await loadTransactions();await loadRecurring();await loadDashboard();toast('Monatsbetrag gespeichert')});
}
function recurringTransactionOverrideDialog(tx){
  openModal(`<h2>${esc(hpText('Einzelnen Serientermin anpassen'))}</h2><p class="muted">${esc(hpText('Diese Änderung gilt nur für diesen Termin. Die Serienvorlage bleibt unverändert.'))}</p><label>${esc(hpText('Termin'))}<input name="due_date" type="date" readonly value="${esc(tx.booking_date)}"></label><label>${esc(hpText('Betrag EUR'))}<input name="amount" type="number" min="0" step="0.01" required value="${Math.abs(Number(tx.amount)).toFixed(2)}"></label><label>${esc(hpText('Notiz'))}<input name="note" value="${esc(tx.note||'')}"></label><small>${esc(hpText('Die Serienänderung ab einem Stichtag erfolgt unter „Wiederkehrende Buchungen“.'))}</small>`,async f=>{await api('/api/recurring/'+tx.recurring_id+'/override',{method:'PUT',body:JSON.stringify({due_date:tx.booking_date,amount:String(f.get('amount')),note:f.get('note')||null})});await loadTransactions();await loadRecurring();await loadDashboard();toast(hpText('Einzeltermin gespeichert'))});
}
async function loadRecurring(){
  try{
    await materializeRecurringDue();
    const rows=await api('/api/recurring');
    const amap=Object.fromEntries(accountsCache.map(a=>[a.id,a.name]));
    const freqLabel={monthly:'Monatlich',weekly:'Wöchentlich',yearly:'Jährlich',daily:'Täglich'};
    if($('txRecurringCount'))$('txRecurringCount').textContent=String(rows.length);
    $('recBody').innerHTML=rows.map(r=>`<tr><td>${esc(formatDateValue(r.next_date))}</td><td class="recurring-name-cell"><b>${esc(r.name)}</b><small class="recurring-series-meta">${esc(hpT('recurring.series','Serie'))} #${r.series_id} · ${esc(hpT('recurring.since','seit'))} ${esc(formatDateValue(r.first_date))}${(r.journal_count??r.executed_count)?` · ${r.journal_count??r.executed_count}× ${esc(hpT('recurring.inJournal','in Buchungen'))}`:''}</small>${r.future_change_from?`<small class="recurring-future-change">${esc(hpText('Änderung vorgemerkt ab'))} ${esc(formatDateValue(r.future_change_from))}</small>`:''}</td><td>${esc(amap[r.account_id]||'?')}</td><td>${esc(hpText(freqLabel[r.frequency]||r.frequency))}</td><td>${r.valid_until?esc(formatDateValue(r.valid_until)):hpText('Unbegrenzt')}</td><td class="right amount ${r.amount<0?'neg':'pos'}">${fmt(r.amount)}</td><td class="actions"><button data-redit="${r.id}">${esc(hpText('Serie bearbeiten'))}</button><button class="ghost" data-roverride="${r.id}">${esc(hpText('Monat anpassen'))}</button><button class="ghost" data-stop="${r.id}">${esc(hpText('Stoppen'))}</button><button class="ghost danger-outline" data-rdel="${r.id}">${esc(hpText('Serie löschen'))}</button></td></tr>`).join('')||'<tr><td colspan="7">Keine wiederkehrenden Buchungen.</td></tr>';
    document.querySelectorAll('[data-redit]').forEach(b=>b.onclick=()=>recDialog(rows.find(r=>r.id===Number(b.dataset.redit))));
    document.querySelectorAll('[data-roverride]').forEach(b=>b.onclick=()=>recurringOverrideDialog(rows.find(r=>r.id===Number(b.dataset.roverride))));
    document.querySelectorAll('[data-stop]').forEach(b=>b.onclick=async()=>{if(hpConfirm('Serie ab jetzt stoppen? Zukünftige geplante Serienbuchungen werden entfernt; bereits ausgeführte Buchungen bleiben erhalten.')){await api('/api/recurring/'+b.dataset.stop,{method:'DELETE'});await loadRecurring();await loadTransactions();await loadDashboard()}});
    document.querySelectorAll('[data-rdel]').forEach(b=>b.onclick=async()=>{if(hpConfirm('Wiederholungsserie vollständig löschen? Zukünftige geplante Serienbuchungen werden entfernt; bereits ausgeführte Buchungen bleiben erhalten.')){await api('/api/recurring/'+b.dataset.rdel+'?hard=true',{method:'DELETE'});await loadRecurring();await loadTransactions();await loadDashboard();toast('Serie gelöscht – ausgeführte Buchungen bleiben erhalten.')}})
  }catch(err){
    if($('txRecurringCount'))$('txRecurringCount').textContent='!';
    $('recBody').innerHTML=`<tr><td colspan="7"><span class="neg">Serien konnten nicht geladen werden:</span> ${esc(err.message)}</td></tr>`
  }
}



function budgetStrategyInfo(){return {
  hybrid:{title:hpT('budget.strategy.hybrid.title','Hybrid'),description:hpT('budget.strategy.hybrid.description','Freier Modus: Du kombinierst Kategorie-Limits, ein Gesamtbudget und Sparziele so, wie es zu deinem Haushalt passt. Gut, wenn dein Einkommen oder deine Ausgaben schwanken.')},
  zero_based:{title:hpT('budget.strategy.zeroBased.title','Zero-Based Budgeting'),description:hpT('budget.strategy.zeroBased.description','Jeder erwartete Euro bekommt vor Monatsbeginn eine Aufgabe. Du verteilst die erwarteten Einnahmen auf Kategorien und Sparen, bis „nicht verplant“ möglichst 0 € beträgt.')},
  envelope:{title:hpT('budget.strategy.envelope.title','Envelope / Umschlag'),description:hpT('budget.strategy.envelope.description','Für jede Ausgabenkategorie legst du einen festen Topf fest. HaushaltPro zeigt pro Topf, wie viel bereits verbraucht und wie viel noch verfügbar ist.')},
  '50_30_20':{title:hpT('budget.strategy.503020.title','50/30/20-Regel'),description:hpT('budget.strategy.503020.description','Richtwert für das Nettoeinkommen: 50 % Grundbedarf, 30 % Wünsche, 20 % Sparen/Rücklagen. Ordne Budgets den Bereichen Bedarf, Wünsche oder Sparen zu.')},
  pay_yourself_first:{title:hpT('budget.strategy.pyf.title','Pay Yourself First'),description:hpT('budget.strategy.pyf.description','Sparen kommt zuerst. Lege zuerst ein Budget im Bereich „Sparen/Rücklagen“ fest; nur der Rest der erwarteten Einnahmen steht für Ausgaben zur Verfügung.')}
}}
function budgetBucketLabels(){return {free:hpT('budget.bucket.free','Frei'),needs:hpT('budget.bucket.needs','Grundbedarf'),wants:hpT('budget.bucket.wants','Wünsche'),savings:hpT('budget.bucket.savings','Sparen/Rücklagen')}}
function budgetDialog(b=null,strategy='hybrid'){
  const bucket=b?.bucket||((strategy==='pay_yourself_first')?'savings':'free');
  openModal(`<h2>${b?'Budget bearbeiten':'Budget anlegen'}</h2><label>Monat<input name="month" type="month" value="${b?.month||monthValue('budgetMonthName','budgetYear')}" required></label><label>Kategorie<select name="category_id">${categoryOptions(b?.category_id)}</select><small>„Keine Kategorie“ bedeutet Gesamtbudget des Monats.</small></label><label>Betrag EUR<input name="amount" type="number" min="0" step="0.01" required value="${b?.amount??''}"></label><label>Bereich<select name="bucket">${Object.entries(budgetBucketLabels()).map(([k,v])=>`<option value="${k}" ${bucket===k?'selected':''}>${v}</option>`).join('')}</select><small>Für 50/30/20 und Pay Yourself First wird dieser Bereich ausgewertet.</small></label><label>Notiz<input name="note" value="${esc(b?.note||'')}"></label>`,async f=>{const body={month:f.get('month'),category_id:f.get('category_id')?Number(f.get('category_id')):null,amount:String(f.get('amount')),strategy:$('budgetStrategy').value,bucket:f.get('bucket'),note:f.get('note')||null};await api(b?'/api/budgets/'+b.id:'/api/budgets',{method:b?'PUT':'POST',body:JSON.stringify(body)});setMonthControls('budgetMonthName','budgetYear',f.get('month'));await loadBudgets()})
}
function renderBudgetStrategy(data){
  const infos=budgetStrategyInfo(),info=infos[data.strategy]||infos.hybrid;$('budgetStrategy').value=data.strategy;$('budgetStrategyTitle').textContent=info.title;$('budgetStrategyDescription').textContent=info.description;$('budgetIncome').textContent=fmt(data.expected_income);$('budgetAllocated').textContent=fmt(data.category_budget_total);$('budgetSpent').textContent=fmt(data.booked_expense);
  const m=data.strategy_metrics||{};let html='';
  if(data.strategy==='zero_based')html=`<span>${hpT('budget.metric.allocated','Verplant')} <b>${fmt(m.allocated)}</b></span><span>${hpT('budget.metric.unallocated','Nicht verplant')} <b class="${Number(m.unallocated)<0?'amount neg':''}">${fmt(m.unallocated)}</b></span>`;
  else if(data.strategy==='envelope')html=`<span>${hpT('budget.metric.envelopes','In Umschlägen')} <b>${fmt(m.allocated)}</b></span><span>${hpT('budget.metric.available','Noch verfügbar')} <b>${fmt(m.remaining)}</b></span>`;
  else if(data.strategy==='50_30_20')html=`<span>${hpT('budget.metric.needs','Bedarf')}: ${hpT('budget.metric.target','Ziel')} ${fmt(m.targets?.needs)} · ${hpT('budget.metric.planned','geplant')} ${fmt(m.allocated?.needs)}</span><span>${hpT('budget.metric.wants','Wünsche')}: ${hpT('budget.metric.target','Ziel')} ${fmt(m.targets?.wants)} · ${hpT('budget.metric.planned','geplant')} ${fmt(m.allocated?.wants)}</span><span>${hpT('budget.metric.savings','Sparen')}: ${hpT('budget.metric.target','Ziel')} ${fmt(m.targets?.savings)} · ${hpT('budget.metric.planned','geplant')} ${fmt(m.allocated?.savings)}</span>`;
  else if(data.strategy==='pay_yourself_first')html=`<span>${hpT('budget.metric.saveFirst','Sparen zuerst')} <b>${fmt(m.savings_planned)}</b></span><span>${hpT('budget.metric.afterSavings','Danach verfügbar')} <b>${fmt(m.after_savings)}</b></span>`;
  else html=`<span>${hpT('budget.metric.plannedCategories','Geplante Kategorien')} <b>${fmt(m.allocated)}</b></span><span>${hpT('budget.metric.expectedIncome','Erwartete Einnahmen')} <b>${fmt(m.income)}</b></span>`;
  $('budgetStrategyMetrics').innerHTML=html;
}
async function loadBudgets(){const budgetMonth=monthValue('budgetMonthName','budgetYear');const data=await api('/api/budgets?month='+encodeURIComponent(budgetMonth));renderBudgetStrategy(data);const rows=data.entries||[];$('budgetList').innerHTML=rows.length?rows.map(b=>`<div class="budget-row"><div><b>${esc(b.category_name?categoryDisplayName(b.category_name):hpText('Gesamtbudget'))}</b><small>${esc(budgetBucketLabels()[b.bucket]||hpT('budget.bucket.free','Frei'))}${b.note?' · '+esc(b.note):''}</small></div><div class="budget-progress"><div><span>Budget ${fmt(b.amount)}</span><span>Gebucht ${fmt(b.spent)}</span><span>Rest <b class="${Number(b.remaining)<0?'amount neg':'amount pos'}">${fmt(b.remaining)}</b></span></div><progress max="100" value="${Math.min(100,Math.max(0,Number(b.usage_pct||0)))}"></progress></div><div class="actions"><button data-bedit="${b.id}">Bearbeiten</button><button class="ghost danger-outline" data-bdel="${b.id}">Löschen</button></div></div>`).join(''):'<p class="muted">Noch keine Budgets für diesen Monat. Lege für wichtige Ausgabenkategorien ein Limit fest.</p>';document.querySelectorAll('[data-bedit]').forEach(b=>b.onclick=()=>budgetDialog(rows.find(x=>x.id===Number(b.dataset.bedit)),data.strategy));document.querySelectorAll('[data-bdel]').forEach(b=>b.onclick=async()=>{if(hpConfirm('Budget löschen?')){await api('/api/budgets/'+b.dataset.bdel,{method:'DELETE'});await loadBudgets()}})}
$('budgetReload').onclick=loadBudgets;$('newBudget').onclick=()=>budgetDialog(null,$('budgetStrategy').value);$('budgetStrategy').onchange=async e=>{await api('/api/settings/budget_strategy',{method:'PUT',body:JSON.stringify({value:e.target.value})});await loadBudgets()};


function renderCategories(items=[]){if(!$('categoryList'))return;const sums=new Map(items.map(x=>[String(x.category_id),Number(x.amount)]));$('categoryList').innerHTML=categoriesCache.map(c=>`<div class="row category-row"><span><span class="category-title"><b>${esc(categoryDisplayName(c.name))}</b><span class="category-type">${esc(categoryTypeLabel(c.direction))}</span></span></span><span class="category-sum ${c.direction==='expense'?'amount neg':'amount pos'}">${fmt(sums.get(String(c.id))||0)}</span></div>`).join('')||'<p class="muted">Keine Kategorien.</p>'}
function reportFlowMeta(value,income,kind='share'){
  const n=Number(value||0),inc=Number(income||0);
  if(kind==='income')return hpLang()==='en'?'100 % income':'100 % Einnahmen';
  if(kind==='net'){
    if(n<0)return hpLang()==='en'?`Deficit ${fmt(Math.abs(n))}`:`Defizit ${fmt(Math.abs(n))}`;
    if(inc>0)return `${Number(n/inc*100).toLocaleString(hpLocale(),{maximumFractionDigits:1})} % ${hpLang()==='en'?'remaining':'übrig'}`;
    return hpLang()==='en'?'No income basis':'Keine Einnahmen als Basis';
  }
  if(inc>0)return `${Number(n/inc*100).toLocaleString(hpLocale(),{maximumFractionDigits:1})} % ${hpLang()==='en'?'of income':'der Einnahmen'}`;
  return hpLang()==='en'?'No income basis':'Keine Einnahmen als Basis';
}
function setReportFlowMeasure(id,value,maxValue){
  const el=$(id);if(!el)return;
  const v=Math.abs(Number(value||0));
  const ratio=maxValue>0?(v/maxValue):0;
  const pct=maxValue>0?Math.max(24,Math.min(100,Math.round(26+ratio*74))):24;
  const thickness=Math.max(6,Math.min(20,Math.round(6+ratio*14)));
  const head=Math.max(6,Math.min(12,Math.round(thickness*.72)));
  el.style.setProperty('--flow-width',pct+'%');
  el.style.setProperty('--flow-thickness',thickness+'px');
  el.style.setProperty('--flow-head-main',head+'px');
  const span=el.querySelector('span');
  if(span){span.style.width=pct+'%';span.style.height=thickness+'px';span.style.minHeight=thickness+'px';}
}
function setReportFlowNodeScale(id,value,maxValue){
  const el=$(id);if(!el)return;
  const v=Math.abs(Number(value||0));
  const ratio=maxValue>0?(v/maxValue):0;
  const h=Math.round(96+ratio*72);
  el.style.minHeight=h+'px';
  el.style.height='auto';
}
function reportFlowSentence(income,expense,savings,net){
  if(hpLang()==='en'){
    if(net>=0)return `Income ${fmt(income)} flows into the balance. From there ${fmt(expense)} goes to expenses and ${fmt(savings)} to savings, leaving ${fmt(net)}.`;
    return `Income ${fmt(income)} is lower than expenses plus savings. Expenses ${fmt(expense)}, savings ${fmt(savings)}, deficit ${fmt(Math.abs(net))}.`;
  }
  if(net>=0)return `Die Einnahmen ${fmt(income)} fließen ins Guthaben. Von dort gehen ${fmt(expense)} in Ausgaben und ${fmt(savings)} ins Sparen – ${fmt(net)} bleiben übrig.`;
  return `Die Einnahmen ${fmt(income)} reichen nicht für Ausgaben plus Sparen. Ausgaben ${fmt(expense)}, Sparen ${fmt(savings)}, Defizit ${fmt(Math.abs(net))}.`;
}
function flowCategoryRows(items,direction){
  return (items||[])
    .filter(x=>x.direction===direction&&Number(x.amount)>0)
    .map(x=>({category_name:categoryDisplayName(x.category_name),amount:Number(x.amount||0)}))
    .sort((a,b)=>b.amount-a.amount);
}
function flowArrowGeometry(amount,groupTotal,groupMax){
  const safeAmount=Math.max(0,Number(amount)||0);
  const total=Math.max(0,Number(groupTotal)||0);
  const maxAmount=Math.max(0,Number(groupMax)||0);
  const share=total>0?(safeAmount/total*100):0;
  const safeShare=Math.max(0,Math.min(100,share));
  const relative=maxAmount>0?Math.max(0,Math.min(1,safeAmount/maxAmount)):0;

  // Länge = echter Anteil an der Gruppe. Eine kleine Mindestlänge hält 1–2-%-Werte sichtbar.
  const endX=Number(Math.max(12,safeShare).toFixed(2));
  // Dicke = Betrag relativ zur größten Kategorie derselben Gruppe.
  // Das ist reine Darstellungs-Skalierung; die Prozentzahl bleibt Kategorie / Gruppensumme.
  // So wird die größte Kategorie klar am dicksten, während kleinere Werte sichtbar abstufen.
  const thickness=Number((4+relative*56).toFixed(1));
  const centerY=32;
  const top=Number((centerY-thickness/2).toFixed(2));
  const bottom=Number((centerY+thickness/2).toFixed(2));
  const head=Math.max(4,Math.min(10,endX*.28));
  const neckX=Number(Math.max(0,endX-head).toFixed(2));
  const points=`0,${top} ${neckX},${top} ${endX},${centerY} ${neckX},${bottom} 0,${bottom}`;
  return {share,safeShare,relative,endX,thickness,points};
}
function renderFlowCategoryStack(targetId,items,total,direction,globalMax){
  const el=$(targetId);if(!el)return;
  const isIncome=direction==='income',isSavings=direction==='savings';
  const noLabel=hpLang()==='en'
    ?(isIncome?'No income categories':isSavings?'No savings categories':'No expense categories')
    :(isIncome?'Keine Einnahmekategorien':isSavings?'Keine Sparkategorien':'Keine Ausgabenkategorien');
  if(!items.length){el.innerHTML=`<p class="muted flow-category-empty">${esc(noLabel)}</p>`;return}

  // Die sichtbaren Kategorien sind die Prozentbasis. Damit ergeben alle hier
  // dargestellten Kategorien einer Gruppe zusammen exakt 100 % (Rundung ausgenommen).
  const categoryTotal=items.reduce((sum,x)=>sum+Math.max(0,Number(x.amount)||0),0);
  const groupMax=items.reduce((m,x)=>Math.max(m,Math.max(0,Number(x.amount)||0)),0);

  el.innerHTML=items.map(x=>{
    const amount=Math.max(0,Number(x.amount||0));
    const g=flowArrowGeometry(amount,categoryTotal,groupMax);
    const cls=isIncome?'income':isSavings?'savings':'expense';
    const shareDigits=g.share>0&&g.share<1?2:1;
    const shareText=g.share.toLocaleString(hpLocale(),{minimumFractionDigits:0,maximumFractionDigits:shareDigits});
    const details=`<div class="flow-category-label"><b>${esc(x.category_name)}</b><span>${fmt(amount)}</span><small>${shareText} %</small></div>`;
    const title=esc(`${x.category_name}: ${shareText} % · ${g.thickness}px`);
    const arrow=`<div class="flow-category-arrow" data-flow-share="${g.share.toFixed(4)}" data-flow-relative="${g.relative.toFixed(4)}" data-flow-thickness="${g.thickness}" data-flow-group="${cls}" title="${title}" aria-label="${shareText} %"><svg class="flow-category-svg" viewBox="0 0 100 64" preserveAspectRatio="none" aria-hidden="true" focusable="false"><polygon points="${g.points}"></polygon></svg></div>`;
    return `<div class="flow-category-path ${cls}">${details}${arrow}</div>`;
  }).join('');
}
function renderReportFlow(r,period,anchorLabel){
  const income=Number(r?.income||0),expense=Number(r?.expense||0),savings=Number(r?.savings||0),net=Number(r?.net||0);
  const values={reportFlowIncome:income,reportFlowExpense:expense,reportFlowSavings:savings,reportFlowNet:net};
  Object.entries(values).forEach(([id,value])=>{const el=$(id);if(el)el.textContent=fmt(value)});
  const periodEl=$('reportFlowPeriodLabel');if(periodEl)periodEl.textContent=anchorLabel||'–';
  const incomeMeta=$('reportFlowIncomeMeta');if(incomeMeta)incomeMeta.textContent=reportFlowMeta(income,income,'income');
  const expenseMeta=$('reportFlowExpenseMeta');if(expenseMeta)expenseMeta.textContent=reportFlowMeta(expense,income);
  const savingsMeta=$('reportFlowSavingsMeta');if(savingsMeta)savingsMeta.textContent=reportFlowMeta(savings,income);
  const netMeta=$('reportFlowNetMeta');if(netMeta)netMeta.textContent=reportFlowMeta(net,income,'net');
  const summary=$('reportFlowSummary');if(summary)summary.textContent=reportFlowSentence(income,expense,savings,net);
  const balance=$('reportFlowBalanceCard');if(balance)balance.classList.toggle('negative',net<0);
  const maxValue=Math.max(Math.abs(income),Math.abs(expense),Math.abs(savings),Math.abs(net),1);
  setReportFlowNodeScale('reportFlowIncomeNode',income,maxValue);
  setReportFlowNodeScale('reportFlowExpenseNode',expense,maxValue);
  setReportFlowNodeScale('reportFlowSavingsNode',savings,maxValue);
  setReportFlowNodeScale('reportFlowBalanceCard',Math.max(Math.abs(net),Math.min(maxValue,Math.abs(expense)+Math.abs(savings))),Math.max(maxValue,Math.abs(expense)+Math.abs(savings),1));
  const items=r?.items||[];
  renderFlowCategoryStack('reportFlowIncomeCategories',flowCategoryRows(items,'income'),income,'income',maxValue);
  renderFlowCategoryStack('reportFlowExpenseCategories',flowCategoryRows(items,'expense'),expense,'expense',maxValue);
  renderFlowCategoryStack('reportFlowSavingsCategories',flowCategoryRows(items,'savings'),savings,'savings',maxValue);
}

const DONUT_COLORS=['#0f766e','#2563eb','#9333ea','#c2410c','#be123c','#4d7c0f','#0369a1','#7c3aed','#b45309','#047857','#475569','#a21caf'];
function drawDonut(canvasId,legendId,items){
  const canvas=$(canvasId),legend=$(legendId);if(!canvas||!legend)return;
  const rows=(items||[]).filter(x=>Number(x.amount)>0),total=rows.reduce((sum,x)=>sum+Number(x.amount),0);
  const state=canvas._donutState||(canvas._donutState={active:null});
  const setup=()=>{const rect=canvas.getBoundingClientRect(),size=Math.max(220,Math.min(310,Math.floor(rect.width||280))),dpr=Math.max(1,devicePixelRatio||1);canvas.width=size*dpr;canvas.height=size*dpr;canvas.style.height=size+'px';return {size,dpr}};
  const paint=()=>{const {size,dpr}=setup(),ctx=canvas.getContext('2d');ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,size,size);const cx=size/2,cy=size/2,r=size*.39,inner=size*.23,css=getComputedStyle(document.documentElement),text=css.getPropertyValue('--text').trim(),muted=css.getPropertyValue('--muted').trim(),line=css.getPropertyValue('--line').trim();
    if(!total){ctx.strokeStyle=line;ctx.lineWidth=r-inner;ctx.beginPath();ctx.arc(cx,cy,(r+inner)/2,0,Math.PI*2);ctx.stroke();ctx.fillStyle=muted;ctx.textAlign='center';ctx.textBaseline='middle';ctx.font='13px system-ui';ctx.fillText('Keine Daten',cx,cy);legend.innerHTML='<p class="muted">Keine Werte im Zeitraum.</p>';return}
    let start=-Math.PI/2;const segments=[];rows.forEach((x,i)=>{const fraction=Number(x.amount)/total,end=start+fraction*Math.PI*2,mid=(start+end)/2,active=state.active===i,off=active?9:0,ox=Math.cos(mid)*off,oy=Math.sin(mid)*off,outer=active?r+6:r;ctx.save();ctx.translate(ox,oy);ctx.beginPath();ctx.arc(cx,cy,outer,start,end);ctx.arc(cx,cy,inner,end,start,true);ctx.closePath();ctx.fillStyle=DONUT_COLORS[i%DONUT_COLORS.length];ctx.shadowColor=active?'rgba(15,23,42,.28)':'transparent';ctx.shadowBlur=active?12:0;ctx.fill();ctx.restore();segments.push({start,end,mid});start=end});canvas._donutSegments={segments,cx,cy,r,inner,size};
    const active=state.active!==null?rows[state.active]:null,pct=active?Number(active.amount)/total*100:null;ctx.fillStyle=text;ctx.textAlign='center';ctx.textBaseline='middle';ctx.font='700 18px system-ui';ctx.fillText(active?fmt(active.amount):fmt(total),cx,cy-9);ctx.fillStyle=muted;ctx.font='12px system-ui';ctx.fillText(active?`${categoryDisplayName(active.category_name)} · ${pct.toLocaleString(hpLocale(),{minimumFractionDigits:1,maximumFractionDigits:1})} %`:hpText('Gesamt'),cx,cy+16);
    legend.querySelectorAll('.donut-legend-row').forEach((el,i)=>el.classList.toggle('active',state.active===i));
  };
  legend.innerHTML=rows.map((x,i)=>{const pct=Number(x.amount)/total*100;return `<button type="button" class="donut-legend-row" data-donut-index="${i}"><span class="donut-key"><i style="--donut-color:${DONUT_COLORS[i%DONUT_COLORS.length]}"></i><b>${esc(categoryDisplayName(x.category_name))}</b></span><span><strong>${fmt(x.amount)}</strong><small>${pct.toLocaleString(hpLocale(),{minimumFractionDigits:1,maximumFractionDigits:1})} %</small></span></button>`}).join('');
  const setActive=i=>{state.active=i;paint()};
  legend.querySelectorAll('[data-donut-index]').forEach(el=>{const i=Number(el.dataset.donutIndex);el.onmouseenter=()=>setActive(i);el.onmouseleave=()=>setActive(null);el.onclick=()=>setActive(state.active===i?null:i)});
  const hit=e=>{const g=canvas._donutSegments;if(!g)return null;const rect=canvas.getBoundingClientRect(),x=e.clientX-rect.left-g.cx,y=e.clientY-rect.top-g.cy,dist=Math.hypot(x,y);if(dist<g.inner-12||dist>g.r+24)return null;let a=Math.atan2(y,x);while(a< -Math.PI/2)a+=Math.PI*2;for(let i=0;i<g.segments.length;i++){let {start,end}=g.segments[i];while(end<start)end+=Math.PI*2;let aa=a;while(aa<start)aa+=Math.PI*2;if(aa>=start&&aa<=end)return i}return null};
  canvas.onpointermove=e=>{if(e.pointerType==='touch')return;setActive(hit(e))};canvas.onpointerleave=e=>{if(e.pointerType!=='touch')setActive(null)};canvas.onpointerdown=e=>{const i=hit(e);setActive(state.active===i?null:i)};paint();
}
async function loadReports(){
  const period=$('reportPeriod').value,anchor=period==='month'?monthValue('reportMonthName','reportYear')+'-01':$('reportYear').value+'-01-01';$('reportMonthName').hidden=period!=='month';
  const r=await cachedApi('/api/reports/categories?period='+period+'&anchor='+encodeURIComponent(anchor),25000);$('reportIncome').textContent=fmt(r.income);$('reportExpense').textContent=fmt(r.expense);$('reportSavings').textContent=fmt(r.savings||0);$('reportNet').textContent=fmt(r.net);
  const income=Number(r.income||0),expense=Number(r.expense||0),savings=Number(r.savings||0),net=Number(r.net??(income-expense-savings));
  // Derive the displayed rate from the same visible report figures. This prevents
  // a stale/legacy savings_rate_pct from showing 0 % while savings are visible.
  const totalSaved=Number.isFinite(Number(r.total_saved))?Number(r.total_saved):(savings+Math.max(0,net));
  const savingsRate=income>0?(totalSaved/income*100):0;
  $('reportSavingsRate').textContent=`${savingsRate.toLocaleString(hpLocale(),{maximumFractionDigits:1})} %`;
  const yearly=period==='year';
  $('reportSavingsRateLabel').textContent=hpLang()==='en'?(yearly?'Savings rate year':'Savings rate month'):(yearly?'Sparquote Jahr':'Sparquote Monat');
  $('reportAvgSavingsLabel').textContent=hpLang()==='en'?(yearly?'Ø savings per month':'Ø savings per day'):(yearly?'Ø Sparen pro Monat':'Ø Sparen pro Tag');
  $('reportAvgSavings').textContent=fmt(r.average_saved||0);
  const expenseItems=r.items.filter(x=>x.direction==='expense'),incomeItems=r.items.filter(x=>x.direction==='income'),row=x=>`<div class="row"><span><b>${esc(categoryDisplayName(x.category_name))}</b></span><strong>${fmt(x.amount)}</strong></div>`;
  $('reportExpenses').classList.add('report-list');$('reportIncomes').classList.add('report-list');$('reportExpenses').innerHTML=expenseItems.map(row).join('')||`<p class="muted">${esc(hpLang()==='en'?'No expenses.':'Keine Ausgaben.')}</p>`;$('reportIncomes').innerHTML=incomeItems.map(row).join('')||`<p class="muted">${esc(hpLang()==='en'?'No income.':'Keine Einnahmen.')}</p>`;$('reportSavingsList').innerHTML=r.items.filter(x=>x.direction==='savings').map(row).join('')||`<p class="muted">${esc(hpLang()==='en'?'No savings.':'Kein Sparen.')}</p>`;
  const anchorLabel=period==='month'?formatMonthValue(anchor.slice(0,7)):String(anchor.slice(0,4));
  renderReportFlow(r, period, anchorLabel);
  drawDonut('expenseDonut','expenseDonutLegend',expenseItems);drawDonut('incomeDonut','incomeDonutLegend',incomeItems);renderCategories(r.items)
}
$('reportReload').onclick=loadReports;$('reportPeriod').onchange=loadReports;$('reportMonthName').onchange=loadReports;$('reportYear').onchange=loadReports;$('newCategory').onclick=()=>openModal(`<h2>Kategorie anlegen</h2><label>Name<input name="name" required></label><label>Typ<select name="direction"><option value="expense">Ausgabe</option><option value="income">Einnahme</option><option value="savings">Sparen</option></select></label>`,async f=>{await api('/api/categories',{method:'POST',body:JSON.stringify({name:f.get('name'),direction:f.get('direction'),parent_id:null})});categoriesCache=await api('/api/categories');loadReports();});
const investmentTypeLabels={stock:'Aktie',etf:'ETF',fund:'Fonds',crypto:'Krypto',p2p:'P2P',fixed_deposit:'Festgeld',manual:'Manuelles Asset'};
function investmentDialog(asset=null){openModal(`<h2>${asset?'Investment bearbeiten':'Investment anlegen'}</h2><label>Name<input name="name" required value="${esc(asset?.name||'')}"></label><label>Symbol<input name="symbol" value="${esc(asset?.symbol||'')}"></label><label>Typ<select name="asset_type">${Object.entries(investmentTypeLabels).map(([k,v])=>`<option value="${k}" ${asset?.asset_type===k?'selected':''}>${v}</option>`).join('')}</select></label><label>Menge<input name="quantity" type="number" min="0" step="any" required value="${asset?.quantity??''}"></label><label>Durchschnittlicher Kaufkurs EUR<input name="purchase_price" type="number" min="0" step="0.000001" required value="${asset?.purchase_price??0}"></label><label>Aktueller Kurs EUR<input name="current_price" type="number" min="0" step="0.000001" required value="${asset?.current_price??0}"></label><label>Gebühren gesamt EUR<input name="fees" type="number" min="0" step="0.01" value="${asset?.fees??0}"></label>`,async f=>{const body={name:f.get('name'),symbol:f.get('symbol')||null,asset_type:f.get('asset_type'),quantity:String(f.get('quantity')),purchase_price:String(f.get('purchase_price')),current_price:String(f.get('current_price')),fees:String(f.get('fees')||'0'),currency:'EUR'};await api(asset?'/api/investments/'+asset.id:'/api/investments',{method:asset?'PUT':'POST',body:JSON.stringify(body)});await loadInvestments()})}
async function loadInvestments(){try{const r=await api('/api/investments');$('invCost').textContent=fmt(r.total_cost);$('invValue').textContent=fmt(r.total_value);$('invPerf').textContent=`${fmt(r.gain)} · ${Number(r.performance_pct).toFixed(2)} %`;$('investmentBody').innerHTML=r.assets.map(a=>`<tr><td><b>${esc(a.name)}</b><small>${esc(a.symbol||'')}</small></td><td>${esc(investmentTypeLabels[a.asset_type]||a.asset_type)}</td><td class="right">${Number(a.quantity).toLocaleString(hpLocale(),{maximumFractionDigits:8})}</td><td class="right">${fmt(a.purchase_price)}</td><td class="right">${fmt(a.current_price)}</td><td class="right">${fmt(a.market_value)}</td><td class="right amount ${a.gain<0?'neg':'pos'}">${fmt(a.gain)} · ${Number(a.performance_pct).toFixed(2)} %</td><td class="actions"><button data-iedit="${a.id}">Bearbeiten</button><button class="ghost" data-idel="${a.id}">Löschen</button></td></tr>`).join('')||'<tr><td colspan="8">Noch keine Investments.</td></tr>';document.querySelectorAll('[data-iedit]').forEach(b=>b.onclick=()=>investmentDialog(r.assets.find(a=>a.id===Number(b.dataset.iedit))));document.querySelectorAll('[data-idel]').forEach(b=>b.onclick=async()=>{if(hpConfirm('Investment löschen?')){await api('/api/investments/'+b.dataset.idel,{method:'DELETE'});loadInvestments()}})}catch(err){if(err.message.includes('deaktiviert'))switchView('settings');else toast(err.message)}}
$('newInvestment').onclick=()=>investmentDialog();

function accountReconcileDialog(account){
  const today=new Date().toISOString().slice(0,10);
  openModal(`<h2>Kontostand abgleichen</h2><p class="muted">${esc(account.name)} · HaushaltPro erwartet aktuell ${fmt(account.balance)}.</p><label>Stichtag<input name="checked_at" type="date" required value="${today}"></label><label>Tatsächlicher Bankstand EUR<input name="actual_balance" type="number" step="0.01" required></label><label>Notiz<input name="note" placeholder="z. B. Kontoauszug"></label><small>Der Abgleich dokumentiert die Differenz. Eine Korrekturbuchung ist optional und wird niemals automatisch erzeugt.</small>`,async f=>{
    const body={actual_balance:String(f.get('actual_balance')),checked_at:f.get('checked_at'),note:f.get('note')||null};
    const r=await api('/api/accounts/'+account.id+'/reconcile',{method:'POST',body:JSON.stringify(body)});
    setTimeout(()=>showReconcileResult(account,r,body),50);
  })
}
function showReconcileResult(account,r,body){
  const sug=(r.suggestions||[]).filter(x=>x.type!=='correction').map(x=>`<div class="row"><span><b>${esc(x.label)}</b><small>${esc(x.reason||'')}</small></span><span>${Math.round(Number(x.confidence||0)*100)} %</span></div>`).join('');
  openModal(`<h2>Abgleich ${esc(account.name)}</h2><div class="mini-metrics"><div><span>Soll</span><strong>${fmt(r.expected)}</strong></div><div><span>Ist</span><strong>${fmt(r.actual)}</strong></div><div><span>Differenz</span><strong class="${Number(r.difference)!==0?'amount neg':''}">${fmt(r.difference)}</strong></div></div>${sug?`<h3>Lokale Vorschläge</h3>${sug}`:''}<p class="muted">Der Matcher arbeitet lokal und nachvollziehbar. Bestätigte Korrekturen erhöhen nur die Trefferquote ähnlicher Abweichungen; es wird kein Cloud-KI-Modell verwendet.</p>${Number(r.difference)!==0?'<label>Korrektur-Bezeichnung<input name="label" value="Kontokorrektur"></label><label class="check"><input name="create" type="checkbox"> Optionale Korrekturbuchung erzeugen</label>':''}`,async f=>{
    if(f.get('create')==='on'){
      const cr=await api('/api/accounts/'+account.id+'/reconcile/correction',{method:'POST',body:JSON.stringify({...body,create_correction:true,label:f.get('label')||'Kontokorrektur'})});
      toast(`Korrekturbuchung ${fmt(cr.difference)} erzeugt`);await loadAccountManager();await loadDashboard();
    }
  })
}
function interactiveMonthlyChart(canvasId,rows,key='end_balance',labelKey='month'){
  const c=$(canvasId);if(!c||!rows?.length)return;
  c._hpRows=rows;c._hpKey=key;c._hpLabelKey=labelKey;
  const state=c._hpState||(c._hpState={hover:null});
  const paint=()=>{
    const wrap=c.parentElement,rect=wrap.getBoundingClientRect(),W=Math.max(340,Math.floor(rect.width||800)),H=Math.max(260,Math.floor(rect.height||380));
    const dpr=Math.max(1,window.devicePixelRatio||1);c.width=Math.floor(W*dpr);c.height=Math.floor(H*dpr);c.style.width=W+'px';c.style.height=H+'px';
    const ctx=c.getContext('2d');ctx.setTransform(dpr,0,0,dpr,0,0);
    const vals=rows.map(x=>Number(x[key]||0)),rawMin=Math.min(...vals),rawMax=Math.max(...vals),rawSpan=Math.max(1,rawMax-rawMin);
    const pv=Math.max(rawSpan*.12,Math.max(Math.abs(rawMax),Math.abs(rawMin),100)*.04),min=rawMin-pv,max=rawMax+pv,span=Math.max(1,max-min);
    const left=88,right=24,top=24,bottom=54,plotW=Math.max(1,W-left-right),plotH=Math.max(1,H-top-bottom);
    const css=getComputedStyle(document.documentElement),fg=css.getPropertyValue('--text').trim(),muted=css.getPropertyValue('--muted').trim(),grid=css.getPropertyValue('--line').trim(),accent=css.getPropertyValue('--accent').trim();
    const xFor=i=>left+(rows.length===1?plotW/2:plotW*i/(rows.length-1)),yFor=v=>top+(max-v)/span*plotH;
    ctx.clearRect(0,0,W,H);ctx.font='12px system-ui';ctx.textBaseline='middle';
    for(let i=0;i<=4;i++){const y=top+plotH*i/4,v=max-span*i/4;ctx.strokeStyle=grid;ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(W-right,y);ctx.stroke();ctx.fillStyle=muted;ctx.textAlign='right';ctx.fillText(fmt(v),left-9,y)}
    rows.forEach((r,i)=>{const x=xFor(i),label=String(r[labelKey]||'').replace(/^\d{4}-/,'');ctx.fillStyle=muted;ctx.textAlign='center';ctx.textBaseline='top';ctx.fillText(label,x,H-bottom+15)});
    ctx.strokeStyle=accent;ctx.lineWidth=2.5;ctx.beginPath();rows.forEach((r,i)=>{const x=xFor(i),y=yFor(Number(r[key]||0));i?ctx.lineTo(x,y):ctx.moveTo(x,y)});ctx.stroke();
    rows.forEach((r,i)=>{ctx.fillStyle=accent;ctx.beginPath();ctx.arc(xFor(i),yFor(Number(r[key]||0)),3,0,Math.PI*2);ctx.fill()});
    if(state.hover!==null&&rows[state.hover]){
      const i=state.hover,r=rows[i],x=xFor(i),v=Number(r[key]||0),y=yFor(v);
      ctx.save();ctx.setLineDash([5,4]);ctx.strokeStyle=muted;ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(x,top);ctx.lineTo(x,H-bottom);ctx.moveTo(left,y);ctx.lineTo(W-right,y);ctx.stroke();ctx.restore();
      ctx.fillStyle=accent;ctx.beginPath();ctx.arc(x,y,5,0,Math.PI*2);ctx.fill();
      ctx.fillStyle=fg;ctx.textAlign='right';ctx.textBaseline='middle';ctx.fillText(fmt(v),left-9,y);
      ctx.textAlign='center';ctx.textBaseline='top';const raw=String(r[labelKey]||'');ctx.fillText(raw,x,H-bottom+31);
      const label=`${raw} · ${fmt(v)}`;ctx.font='12px system-ui';const tw=ctx.measureText(label).width+20,th=30,tx=Math.min(Math.max(left,x-tw/2),W-right-tw),ty=Math.max(top,y-42);
      ctx.fillStyle='rgba(17,24,34,.94)';if(document.documentElement.dataset.theme==='light')ctx.fillStyle='rgba(255,255,255,.97)';
      ctx.strokeStyle=grid;ctx.lineWidth=1;ctx.fillRect(tx,ty,tw,th);ctx.strokeRect(tx,ty,tw,th);ctx.fillStyle=fg;ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(label,tx+tw/2,ty+th/2);
    }
  };
  const hoverAt=clientX=>{const rect=c.getBoundingClientRect(),left=88,right=24,plotW=Math.max(1,rect.width-left-right),x=clientX-rect.left;state.hover=Math.max(0,Math.min(rows.length-1,Math.round((x-left)/plotW*(rows.length-1))));paint()};
  c.onmousemove=e=>hoverAt(e.clientX);c.onmouseleave=()=>{state.hover=null;paint()};c.ontouchmove=e=>{if(e.touches[0])hoverAt(e.touches[0].clientX)};paint();
}
function simpleLineChart(canvasId,rows,key='end_balance'){interactiveMonthlyChart(canvasId,rows,key,'month')}

async function loadPlanningExtras(){
  const month=monthValue('planningMonthName','planningYear');
  const [variance,runway,variability,contracts]=await Promise.all([
    cachedApi('/api/planning/variance?month='+encodeURIComponent(month),25000),cachedApi('/api/planning/runway',25000),cachedApi('/api/analysis/variability?months=12',25000),cachedApi('/api/contracts',25000)
  ]);
  $('planningVarianceTable').innerHTML=variance.rows.length?variance.rows.slice(0,12).map(x=>`<div class="row"><span><b>${esc(categoryDisplayName(x.name))}</b><small>${esc(categoryTypeLabel(x.type))}</small></span><span>Plan ${fmt(x.planned)} · Ist ${fmt(x.actual)} · <b>${fmt(x.difference)}</b>${x.difference_pct===null?'':` · ${Number(x.difference_pct).toFixed(1)} %`}</span></div>`).join(''):'<p class="muted">Noch keine Plan/Ist-Daten.</p>';
  $('runwayLiquid').textContent=fmt(runway.liquid_balance);$('runwayFixed').textContent=fmt(runway.monthly_fixed_costs);$('runwayMonths').textContent=runway.runway_months==null?'–':`${Number(runway.runway_months).toLocaleString(hpLocale(),{maximumFractionDigits:1})} Monate`;
  const labels={income:'Einnahmen',expense:'Ausgaben',savings:'Sparen'};$('variabilityStats').innerHTML=Object.entries(variability.stats).map(([k,v])=>`<div class="row"><span><b>${labels[k]}</b><small>Min ${fmt(v.min)} · Median ${fmt(v.median)} · Max ${fmt(v.max)}</small></span><strong>Ø ${fmt(v.average)}</strong></div>`).join('');
  $('contractsList').innerHTML=contracts.length?contracts.map(c=>{const deadline=c.cancellation_deadline?new Date(c.cancellation_deadline+'T12:00:00'):null,days=deadline?Math.ceil((deadline-new Date())/86400000):null,urgent=days!==null&&days>=0&&days<=60;return `<div class="row ${urgent?'check-warning':''}"><span><b>${esc(c.title)}</b><small>${esc(c.provider||'')}${deadline?' · kündigen bis '+formatDateValue(c.cancellation_deadline):''}${urgent?' · '+days+' Tage':''}</small></span><span><button data-cedit="${c.id}">Bearbeiten</button><button class="ghost" data-cdel="${c.id}">Archivieren</button></span></div>`}).join(''):'<p class="muted">Noch keine Vertragsfristen hinterlegt.</p>';
  document.querySelectorAll('[data-cedit]').forEach(b=>b.onclick=()=>contractDialog(contracts.find(x=>x.id===Number(b.dataset.cedit))));document.querySelectorAll('[data-cdel]').forEach(b=>b.onclick=async()=>{if(hpConfirm('Vertrag archivieren?')){await api('/api/contracts/'+b.dataset.cdel,{method:'DELETE'});loadPlanningExtras()}})
}
async function contractDialog(c=null){
  const rec=await api('/api/recurring');
  const recOpts='<option value="">Keine Verknüpfung</option>'+rec.map(r=>`<option value="${r.series_id||r.id}" ${String(c?.recurring_series_id||'')===String(r.series_id||r.id)?'selected':''}>↻ ${esc(r.name)} · ${fmt(r.amount)}</option>`).join('');
  openModal(`<h2>${c?'Vertrag bearbeiten':'Vertrag anlegen'}</h2><label>Bezeichnung<input name="title" required value="${esc(c?.title||'')}"></label><label>Anbieter<input name="provider" value="${esc(c?.provider||'')}"></label><label>Zugehörige Zahlung<select name="recurring_series_id">${recOpts}</select></label><label>Beginn<input name="start_date" type="date" value="${esc(c?.start_date||'')}"></label><label>Ende<input name="end_date" type="date" value="${esc(c?.end_date||'')}"></label><label>Kündigen bis<input name="cancellation_deadline" type="date" value="${esc(c?.cancellation_deadline||'')}"></label><label>Kündigungsfrist Tage<input name="notice_days" type="number" min="0" value="${c?.notice_days??''}"></label><label>Notiz<input name="notes" value="${esc(c?.notes||'')}"></label>`,async f=>{const body={recurring_series_id:f.get('recurring_series_id')?Number(f.get('recurring_series_id')):null,title:f.get('title'),provider:f.get('provider')||null,start_date:f.get('start_date')||null,end_date:f.get('end_date')||null,cancellation_deadline:f.get('cancellation_deadline')||null,notice_days:f.get('notice_days')?Number(f.get('notice_days')):null,notes:f.get('notes')||null,active:true};await api(c?'/api/contracts/'+c.id:'/api/contracts',{method:c?'PUT':'POST',body:JSON.stringify(body)});await loadPlanningExtras()})
}
async function runWhatIf(){const body={horizon_months:Number($('scenarioHorizon').value),monthly_income_change:String($('scenarioIncome').value||'0'),monthly_expense_change:String($('scenarioExpense').value||'0'),monthly_savings_change:String($('scenarioSavings').value||'0'),one_time_change:String($('scenarioOne').value||'0'),one_time_date:$('scenarioDate').value||null};const r=await api('/api/planning/what-if',{method:'POST',body:JSON.stringify(body)});$('scenarioResult').innerHTML=r.series.map(x=>`<div class="row"><span>${esc(formatMonthValue(x.month))}</span><span>Basis ${fmt(x.baseline_end_balance)} · Szenario <b>${fmt(x.scenario_end_balance)}</b> · Δ ${fmt(x.difference)}</span></div>`).join('')}
async function loadFinanceCheck(){const last=await api('/api/finance-check/last');renderFinanceCheck(last)}
function renderFinanceCheck(r){
  if(!r){$('financeCheckStatus').textContent='Noch nicht geprüft';$('financeCheckErrors').textContent='–';$('financeCheckWarnings').textContent='–';$('financeCheckList').innerHTML='<p class="muted">Noch keine Prüfung ausgeführt.</p>';return}
  $('financeCheckStatus').textContent=r.ok?'OK':'Prüfen';
  $('financeCheckErrors').textContent=r.errors;
  $('financeCheckWarnings').textContent=r.warnings;
  const statusLabel=level=>level==='ok'?'OK':level==='warning'?'Hinweis':'Fehler';
  const statusIcon=level=>level==='ok'?'✓':level==='warning'?'⚠':'✕';
  $('financeCheckList').innerHTML=r.checks.map(x=>`<div class="finance-check-row check-${x.level}"><div class="finance-check-message"><b><span class="finance-check-icon">${statusIcon(x.level)}</span>${esc(x.message)}</b><small class="finance-check-code">${esc(x.code)}</small></div><span class="finance-check-badge finance-check-badge-${x.level}">${statusLabel(x.level)}</span></div>`).join('');
}
function setPlanningMode(){
  const yearly=$('planningPeriod').value==='year';
  $('planningMonthView').hidden=yearly;
  $('planningYearView').hidden=!yearly;
  $('planningMonthName').hidden=yearly;
}
async function loadPlanningYear(){
  const year=Number($('planningYear').value)||nowLocal.getFullYear();
  const annual=await cachedApi('/api/planning/year?year='+year,30000),t=annual.totals||{},last=annual.months?.at(-1);
  $('planningYearIncome').textContent=fmt(t.planned_income||0);
  $('planningYearExpense').textContent=fmt(t.planned_expense||0);
  $('planningYearSavings').textContent=fmt(t.planned_savings||0);
  $('planningYearEnd').textContent=fmt(last?.month_end_balance||0);
  interactiveMonthlyChart('planningYearChart',annual.months||[],'month_end_balance','month');
  $('planningYearSummary').innerHTML=yearSummaryMarkup(annual.months||[]);
}

async function loadPlanning(){
  setPlanningMode();
  if($('planningPeriod').value==='year'){await loadPlanningYear();return;}
  const month=monthValue('planningMonthName','planningYear'),url='/api/planning/overview?month='+encodeURIComponent(month),d=await cachedApi(url,25000);
  $('planningFixedRatio').textContent=Number(d.fixed_cost_ratio_pct||0).toLocaleString(hpLocale(),{maximumFractionDigits:1})+' %';$('planningFixedAmount').textContent='Fixkosten '+fmt(d.fixed_costs);
  $('planningFreeMoney').textContent=fmt(d.free_money);
  const cw=d.cashflow_warning||{}, card=$('cashflowWarningCard'), badge=$('cashflowWarningBadge');
  if(cw.consumption_negative||cw.total_negative){
    card.hidden=false;
    const parts=[];
    if(cw.consumption_negative){
      parts.push(`<div class="cashflow-alert strong"><b>⚠ Negativer Konsum-Cashflow</b><span>Ausgaben übersteigen die Einnahmen um ${fmt(cw.consumption_shortfall)}.</span></div>`);
    }
    if(cw.total_negative && !cw.consumption_negative){
      parts.push(`<div class="cashflow-alert"><b>⚠ Negativer Gesamt-Cashflow</b><span>Nach Sparen sinkt der Kontostand in diesem Monat um ${fmt(cw.total_shortfall)}.</span></div>`);
    } else if(cw.total_negative){
      parts.push(`<div class="cashflow-alert"><b>Gesamt-Cashflow inkl. Sparen</b><span>Monatliches Minus: ${fmt(cw.total_shortfall)}.</span></div>`);
    }
    parts.push(`<div class="row"><span>Konsum-Cashflow</span><strong>${fmt(cw.consumption_cashflow)}</strong></div>`);
    parts.push(`<div class="row"><span>Gesamt-Cashflow inkl. Sparen</span><strong>${fmt(cw.total_cashflow)}</strong></div>`);
    $('cashflowWarningBody').innerHTML=parts.join('');
    badge.textContent=cw.consumption_negative?'Warnung':'Hinweis';
    card.classList.toggle('danger',!!cw.consumption_negative);
    card.classList.toggle('warning',!cw.consumption_negative&&!!cw.total_negative);
  } else {
    card.hidden=true;
    $('cashflowWarningBody').innerHTML='';
    card.classList.remove('danger','warning');
  }
  const pa=d.plan_actual,variance=Number(pa.actual.expense)-Number(pa.planned.expense);$('planningVariance').textContent=fmt(variance);
  $('planningPlanActual').innerHTML=['income','expense','savings'].map(k=>`<div class="row"><span><b>${({income:'Einnahmen',expense:'Ausgaben',savings:'Sparen'})[k]}</b></span><span>Plan ${fmt(pa.planned[k])} · Ist ${fmt(pa.actual[k])}</span></div>`).join('');
  $('planningWarnings').innerHTML=d.liquidity_warnings.length?d.liquidity_warnings.map(x=>`<div class="row"><span><b>${esc(x.account)}</b><small>${formatDateValue(x.date)}</small></span><strong class="amount neg">${fmt(x.balance)}</strong></div>`).join(''):'<p class="muted">In den nächsten zwölf Monaten wird nach aktueller Planung kein Konto negativ.</p>';
  const h=$('forecastHorizon').value||'12',rows=d.forecast[h]||[];simpleLineChart('planningChart',rows);$('planningForecastList').innerHTML=rows.map(x=>`<div class="analysis-month-row"><span>${esc(formatMonthValue(x.month))}</span><strong>${fmt(x.end_balance)}</strong></div>`).join('');

  const con=d.forecast.conservative?.at(-1),opt=d.forecast.optimistic?.at(-1);$('planningScenarios').innerHTML=`<div class="row"><span>Konservativ · 12 Monate</span><strong>${fmt(con?.end_balance)}</strong></div><div class="row"><span>Erwartet · 12 Monate</span><strong>${fmt(d.forecast['12']?.at(-1)?.end_balance)}</strong></div><div class="row"><span>Optimistisch · 12 Monate</span><strong>${fmt(opt?.end_balance)}</strong></div>`;
  $('planningHistory').innerHTML=`<div class="row"><span>Vorjahresmonat Einnahmen</span><strong>${fmt(d.previous_year.income)}</strong></div><div class="row"><span>Vorjahresmonat Ausgaben</span><strong>${fmt(d.previous_year.expense)}</strong></div>`+d.averages.map(x=>`<div class="row"><span>Ø ${x.months} Monate Ausgaben</span><strong>${fmt(x.expense)}</strong></div>`).join('');
  $('planningDeviation').innerHTML=d.forecast_deviation?`<hr><p><b>Prognose-Abweichung</b></p><div class="row"><span>damals prognostiziert</span><strong>${fmt(d.forecast_deviation.forecast)}</strong></div><div class="row"><span>tatsächlich</span><strong>${fmt(d.forecast_deviation.actual)}</strong></div><div class="row"><span>Abweichung</span><strong>${fmt(d.forecast_deviation.difference)}</strong></div>`:'<p class="muted">Für diesen Monat liegt noch kein abgeschlossener Prognose-Snapshot vor. HaushaltPro sammelt diese Daten ab v0.7.0.</p>';
  await loadPlanningExtras();
}
let auditPage=1;
let auditPages=1;
const AUDIT_ACTION_LABELS={
  'account.create':'Konto angelegt','account.update':'Konto geändert','account.month_opening':'Monatsanfang korrigiert',
  'account.reconcile':'Kontostand abgeglichen','account.reconcile_correction':'Korrekturbuchung erzeugt','account.month_opening.delete':'Monatsanfang-Korrektur gelöscht','account.delete':'Konto gelöscht/deaktiviert',
  'transaction.create':'Buchung angelegt','transaction.update':'Buchung geändert','transaction.cancel':'Buchung storniert','transaction.delete':'Buchung gelöscht','transfer.create':'Transfer angelegt','transfer.update':'Transfer geändert','transfer.delete':'Transfer storniert/gelöscht','payee.create':'Empfänger gespeichert','payee.update':'Empfänger umbenannt','payee.delete':'Empfänger gelöscht',
  'category.create':'Kategorie angelegt','recurring.create':'Serie angelegt','recurring.update':'Serie geändert','recurring.version':'Neue Serienversion','recurring.stop':'Serie gestoppt','recurring.delete':'Serie gelöscht','recurring.override':'Monatsbetrag angepasst','recurring.override.delete':'Monatsanpassung gelöscht','recurring.execute':'Serientermin gebucht',
  'import.csv':'CSV importiert','user.create':'Benutzer angelegt','user.membership':'Benutzerrechte geändert','user.approval':'Benutzerfreigabe geändert','user.password_reset':'Benutzerpasswort zurückgesetzt','user.password_change':'Eigenes Passwort geändert','user.delete':'Benutzer gelöscht','book.create':'Haushaltsbuch angelegt','book.rename':'Haushaltsbuch umbenannt','book.delete':'Haushaltsbuch gelöscht','audit.delete':'Audit-Eintrag gelöscht','transaction.bulk_delete':'Buchungen gesammelt gelöscht','budget.create':'Budget angelegt','budget.update':'Budget geändert','budget.delete':'Budget gelöscht','settings.update':'Einstellung geändert',
  'contract.create':'Vertrag angelegt','contract.update':'Vertrag geändert','contract.archive':'Vertrag archiviert',
  'attachment.create':'Beleg hochgeladen','attachment.delete':'Beleg gelöscht','finance_check.run':'Finanz-Check ausgeführt','backup.rotate':'Internes Backup erstellt/rotiert',
  'investment.create':'Investment angelegt','investment.update':'Investment geändert'
};
function formatAuditTimestamp(value){
  return formatDateTimeValue(value);
}
const AUDIT_FIELD_LABELS={
  name:'Name',amount:'Betrag',booking_date:'Buchungsdatum',value_date:'Wertstellung',date:'Datum',
  account_name:'Konto',from_account_name:'Von Konto',to_account_name:'Auf Konto',category_name:'Kategorie',payee:'Empfänger',note:'Notiz',tags:'Tags',splits:'Aufteilungen',
  confidence:'Prognose-Sicherheit',fixed_cost:'Fixkosten',status:'Status',direction:'Richtung',
  type:'Kontotyp',iban:'IBAN',opening_balance:'Start-/Monatsanfang',currency:'Währung',start_date:'Startdatum',
  next_date:'Nächster Termin',frequency:'Intervall',valid_from:'Gültig ab',valid_until:'Gültig bis',max_amount:'Maximalbetrag',
  month:'Monat',strategy:'Budgetmethode',bucket:'Topf',category_id:'Kategorie-ID',value:'Wert',
  title:'Titel',provider:'Anbieter',end_date:'Vertragsende',cancellation_deadline:'Kündigen bis',notice_days:'Kündigungsfrist (Tage)',notes:'Notiz',active:'Aktiv',
  symbol:'Symbol',asset_type:'Asset-Typ',quantity:'Menge',purchase_price_cents:'Kaufpreis',manual_price_cents:'Aktueller Preis',fees_cents:'Gebühren',username:'Benutzer',size_bytes:'Größe',member_count:'Mitglieder'
};
const AUDIT_MONEY_FIELDS=new Set(['amount','opening_balance','max_amount','purchase_price_cents','manual_price_cents','fees_cents','expected','actual','difference']);
function auditFieldLabel(key){return hpText(AUDIT_FIELD_LABELS[key]||key.replaceAll('_',' '))}
function auditFieldValue(key,value){
  if(value===null||value===undefined||value==='')return '—';
  if(AUDIT_MONEY_FIELDS.has(key))return fmt(Number(value)/100);
  if(['booking_date','value_date','date','start_date','next_date','valid_from','valid_until','end_date','cancellation_deadline','month'].includes(key)&&/^\d{4}-\d{2}(?:-\d{2})?$/.test(String(value))){return String(value).length===7?formatMonthValue(value):formatDateValue(value)}
  if(key==='category_name')return categoryDisplayName(value);
  if(key==='fixed_cost'||key==='active')return Number(value)?hpText('Ja'):hpText('Nein');
  if(key==='frequency')return hpText(({monthly:'Monatlich',weekly:'Wöchentlich',yearly:'Jährlich',daily:'Täglich'})[value]||String(value));
  if(key==='confidence')return hpText(({fixed:'Fest',likely:'Wahrscheinlich',estimated:'Geschätzt'})[value]||String(value));
  if(Array.isArray(value)){
    if(key==='tags')return value.join(', ')||'—';
    if(key==='splits')return value.map(v=>`${v.category_id??'–'}: ${AUDIT_MONEY_FIELDS.has('amount')?fmt(Number(v.amount||0)/100):v.amount}`).join(' · ')||'—';
    return value.map(v=>typeof v==='object'?JSON.stringify(v):String(v)).join(', ');
  }
  if(typeof value==='object')return JSON.stringify(value);
  return String(value);
}
function auditLegacyChanges(x){
  const d=x.details||{};
  if(d.changes)return d.changes;
  if(d.before&&d.after){
    const out={};
    const pairs=[['amount','amount'],['booking_date','date'],['category_id','category_id']];
    for(const [oldKey,newKey] of pairs){const old=d.before?.[oldKey],neu=d.after?.[newKey];if(old!==undefined&&neu!==undefined&&old!==neu)out[oldKey]={old,new:neu}}
    return out;
  }
  return {};
}
function auditChangeRows(x){
  const d=x.details||{},changes=auditLegacyChanges(x),keys=Object.keys(changes),parts=[];
  if(keys.length){parts.push(`<div class="audit-changes"><div class="audit-subtitle">Geändert</div>${keys.map(key=>{const ch=changes[key]||{};return `<div class="audit-change-row changed"><span class="audit-field">${esc(auditFieldLabel(key))}</span><span class="audit-values"><s>${esc(auditFieldValue(key,ch.old))}</s><span class="audit-arrow">→</span><strong>${esc(auditFieldValue(key,ch.new))}</strong></span></div>`}).join('')}</div>`)}
  if(d.current&&typeof d.current==='object'){
    const entries=Object.entries(d.current).filter(([key,v])=>!keys.includes(key)&&v!==undefined);
    if(entries.length)parts.push(`<div class="audit-current"><div class="audit-subtitle">Aktueller Stand</div><div class="audit-current-grid">${entries.map(([key,value])=>`<div class="audit-current-row"><span>${esc(auditFieldLabel(key))}</span><strong>${esc(auditFieldValue(key,value))}</strong></div>`).join('')}</div></div>`)
  }
  if(!parts.length&&d.added&&typeof d.added==='object'){
    const entries=Object.entries(d.added).filter(([,v])=>v!==null&&v!==undefined&&v!=='');
    if(entries.length)parts.push(`<div class="audit-changes audit-added-list"><div class="audit-subtitle">Hinzugefügt</div>${entries.map(([key,value])=>`<div class="audit-change-row"><span class="audit-field">${esc(auditFieldLabel(key))}</span><span class="audit-values"><strong class="audit-added">+ ${esc(auditFieldValue(key,value))}</strong></span></div>`).join('')}</div>`)
  }
  if(!parts.length&&d.snapshot&&typeof d.snapshot==='object'){
    const entries=Object.entries(d.snapshot).filter(([key,v])=>key!=='_actor_username'&&v!==undefined);
    if(entries.length)parts.push(`<div class="audit-changes audit-removed-list"><div class="audit-subtitle">Letzter Stand</div>${entries.map(([key,value])=>`<div class="audit-change-row"><span class="audit-field">${esc(auditFieldLabel(key))}</span><span class="audit-values"><s>${esc(auditFieldValue(key,value))}</s></span></div>`).join('')}</div>`)
  }
  if(Array.isArray(d.deleted_items)&&d.deleted_items.length){
    parts.push(`<details class="audit-deleted-items"><summary>${d.deleted_items.length.toLocaleString(hpLocale())} gelöschte Buchungen anzeigen</summary><div class="audit-deleted-list">${d.deleted_items.map(v=>`<div><b>#${v.id} · ${esc(v.name||'Buchung')}</b><span>${esc(v.booking_date?formatDateValue(v.booking_date):'–')} · ${esc(v.account_name||'–')} · ${esc(v.payee||'–')} · ${esc(v.category_name?categoryDisplayName(v.category_name):'–')} · ${fmt(Number(v.amount||0)/100)}</span></div>`).join('')}</div></details>`)
  }
  return parts.join('');
}
function auditDetailsText(x){
  const d=x.details||{},cur=d.current||d.added||d.snapshot||{};
  if(x.entity_type==='transaction'){const bits=[d.name||cur.name||hpText('Buchung'),cur.booking_date?formatDateValue(cur.booking_date):null,cur.account_name,cur.payee,cur.category_name?categoryDisplayName(cur.category_name):null];if(cur.amount!==undefined)bits.push(auditFieldValue('amount',cur.amount));return `Buchung #${x.entity_id||'–'} · `+bits.filter(Boolean).join(' · ')};
  if(x.entity_type==='transfer')return `Transfer #${x.entity_id||'–'} · ${d.name||cur.name||'Transfer'}${cur.booking_date?' · '+formatDateValue(cur.booking_date):''}${cur.from_account_name&&cur.to_account_name?' · '+cur.from_account_name+' → '+cur.to_account_name:''}`;
  if(x.entity_type==='recurring'){const r=d.snapshot||d.current||d.added||{};return `Serie #${x.entity_id||'–'} · ${r.name||d.name||'Wiederkehrende Buchung'}${r.account_name?' · '+r.account_name:''}${r.amount!==undefined?' · '+auditFieldValue('amount',r.amount):''}`};
  if(x.entity_type==='book')return `Haushaltsbuch · ${d.name||cur.name||x.entity_id||'–'}`;
  if(x.entity_type==='user')return `Benutzer · ${d.username||x.entity_id||'–'}`;
  if(d.name)return d.name;if(d.title)return d.title;if(d.filename)return d.filename;if(d.month)return `${hpText('Monat')} ${formatMonthValue(d.month)}`;
  return x.entity_id?`${x.entity_type} #${x.entity_id}`:x.entity_type;
}
async function loadAuditTimeline(reset=false){
  if(reset)auditPage=1;
  const q=$('auditSearch')?.value.trim()||'',pageSize=$('auditPageSize')?.value||'25';
  const d=await api(`/api/audit/timeline?page=${auditPage}&page_size=${encodeURIComponent(pageSize)}${q?'&q='+encodeURIComponent(q):''}`);
  auditPage=d.page||1;auditPages=d.pages||1;
  $('auditCount').textContent=String(d.total||0);
  $('auditChain').textContent=d.chain_ok?'✓ OK':'⚠ Fehler';
  $('auditChain').className=d.chain_ok?'pos':'neg';
  const rows=d.items||[];
  $('auditTimeline').innerHTML=rows.map(x=>`<div class="audit-entry"><div class="audit-dot"></div><div class="audit-content"><div class="audit-head"><strong>${esc(hpText(AUDIT_ACTION_LABELS[x.action]||x.action))}</strong><time>${esc(formatAuditTimestamp(x.created_at))}</time></div><div class="audit-meta"><span class="audit-user">👤 <b>${esc(x.username||'System')}</b></span><span>${esc(auditDetailsText(x))}</span></div>${auditChangeRows(x)}<div class="audit-foot"><small>Audit #${x.id} · Hash ${esc(String(x.entry_hash||'').slice(0,12))}…</small>${d.can_delete?`<button class="ghost danger-outline audit-delete-btn" data-audit-delete="${x.id}" type="button">Logeintrag löschen</button>`:''}</div></div></div>`).join('')||'<p class="muted">Keine passenden Änderungen gefunden.</p>';
  $('auditPageInfo').textContent=`Seite ${auditPage} / ${auditPages}`;
  $('auditFirst').disabled=$('auditPrev').disabled=auditPage<=1;
  $('auditNext').disabled=$('auditLast').disabled=auditPage>=auditPages;
  document.querySelectorAll('[data-audit-delete]').forEach(b=>b.onclick=async()=>{if(!hpConfirm('Diesen Logeintrag endgültig löschen? Die verbleibende Hashkette wird kontrolliert neu aufgebaut.'))return;const expected=hpLang()==='en'?'DELETE':'LÖSCHEN';const entered=hpPrompt(hpText('Zur Bestätigung exakt LÖSCHEN eingeben:'));if(String(entered||'').trim().toUpperCase()!==expected)return;const confirmation=canonicalDeleteConfirmation(entered);try{await api('/api/audit/'+b.dataset.auditDelete,{method:'DELETE',body:JSON.stringify({confirmation})});toast('Logeintrag gelöscht; Hashkette neu aufgebaut');await loadAuditTimeline(true)}catch(err){toast(err.message)}});
}


function roleLabel(role){return role==='owner'?'Eigentümer':role==='editor'?'Bearbeiter':role==='viewer'?'Nur Lesen':'Kein Zugriff'}
async function resetUserPassword(username){const p=hpPrompt(`Neues temporäres Passwort für ${username} (mindestens 12 Zeichen):`);if(!p)return;if(p.length<12){toast('Mindestens 12 Zeichen.');return}if(!hpConfirm(`Passwort von ${username} wirklich zurücksetzen? Alle Sitzungen dieses Benutzers werden beendet.`))return;await api('/api/users/'+encodeURIComponent(username)+'/reset-password',{method:'POST',body:JSON.stringify({new_password:p})});toast('Passwort zurückgesetzt. Neues Passwort sicher an den Benutzer übergeben.');loadUsers()}
async function loadUsers(){if(!$('userAccessList'))return;try{
  const rows=await api('/api/users'),canDelete=currentMe?.system_role==='admin',books=(rows[0]?.manageable_books||currentMe?.books||[]);
  $('userAccessList').innerHTML=rows.map((u,idx)=>{const memberships=u.memberships||{};const bookRows=books.map(b=>{const role=memberships[b.id]||'';return `<div class="membership-row"><div class="membership-book"><b>${esc(b.name)}</b>${b.active?'<small>aktuell geöffnet</small>':''}</div><select data-membership-user="${esc(u.username)}" data-membership-book="${esc(b.id)}"><option value="" ${!role?'selected':''}>Kein Zugriff</option><option value="viewer" ${role==='viewer'?'selected':''}>Nur Lesen</option><option value="editor" ${role==='editor'?'selected':''}>Bearbeiter</option><option value="owner" ${role==='owner'?'selected':''}>Eigentümer</option></select></div>`}).join('');return `<article class="user-admin-card" data-user-row="${idx}"><div class="user-admin-card-head"><div><b>${esc(u.username)}</b><small>${u.system_role==='admin'?'System-Administrator · ':''}${u.book_count} von ${books.length} verwaltbaren Haushaltsbüchern freigegeben</small></div><div class="user-admin-actions"><button class="ghost" data-reset-user="${esc(u.username)}" type="button">Passwort zurücksetzen</button>${canDelete&&u.system_role!=='admin'&&u.username!==currentMe?.username?`<button class="ghost danger-outline" data-delete-user="${esc(u.username)}" type="button">Benutzer löschen</button>`:''}</div></div><div class="membership-grid">${bookRows||'<p class="muted">Keine verwaltbaren Haushaltsbücher.</p>'}</div></article>`}).join('')||'<p class="muted">Keine Benutzer.</p>';
  document.querySelectorAll('[data-membership-user]').forEach(sel=>sel.onchange=async()=>{const old=sel.dataset.currentRole??'',username=sel.dataset.membershipUser,bookId=sel.dataset.membershipBook;sel.disabled=true;try{await api('/api/users/'+encodeURIComponent(username)+'/membership',{method:'PUT',body:JSON.stringify({role:sel.value||null,book_id:bookId})});toast('Rechte gespeichert');await loadUsers()}catch(err){toast(err.message);await loadUsers()}finally{sel.disabled=false}});
  document.querySelectorAll('[data-reset-user]').forEach(b=>b.onclick=()=>resetUserPassword(b.dataset.resetUser));document.querySelectorAll('[data-delete-user]').forEach(b=>b.onclick=async()=>{const username=b.dataset.deleteUser;if(!hpConfirm(`Benutzer ${username} dauerhaft löschen? Zugriffe auf alle Haushaltsbücher werden entfernt.`))return;try{await api('/api/users/'+encodeURIComponent(username),{method:'DELETE'});toast('Benutzer gelöscht');await loadUsers();await loadAuditTimeline(true)}catch(err){toast(err.message)}})
}catch(err){$('userAccessList').innerHTML='<p class="muted">'+esc(err.message)+'</p>'}}
$('newUser').onclick=()=>{const books=currentMe?.books||[],opts=books.map(b=>`<option value="${esc(b.id)}">${esc(b.name)}</option>`).join('');openModal(`<h2>Benutzer anlegen</h2><label>Benutzername<input name="username" required maxlength="64"></label><label>Temporäres Passwort<input name="password" type="password" minlength="12" required></label><label>Erste Freigabe für Haushaltsbuch<select name="book_id">${opts}</select></label><label>Rechte<select name="role"><option value="editor">Bearbeiter</option><option value="viewer">Nur Lesen</option><option value="owner">Eigentümer</option></select></label><small class="muted">Nach dem Anlegen kannst du dem Benutzer in der Übersicht beliebig viele weitere Haushaltsbücher zuweisen.</small>`,async f=>{await api('/api/users',{method:'POST',body:JSON.stringify({username:f.get('username'),password:f.get('password'),role:f.get('role'),book_id:f.get('book_id')})});await loadUsers()})};
$('reloadUsers').onclick=loadUsers;
async function loadPayeePresets(){
  payeePresetsCache=await api('/api/payees');if(!$('payeePresetList'))return;
  $('payeePresetList').innerHTML=payeePresetsCache.length?payeePresetsCache.map(p=>`<div class="row payee-preset-row"><span><b>${esc(p.name)}</b><small>${p.usage_count}× verwendet</small></span><span><button class="ghost" data-payee-edit="${p.id}">Umbenennen</button><button class="ghost danger-outline" data-payee-delete="${p.id}">Löschen</button></span></div>`).join(''):'<p class="muted">Noch keine Empfänger gespeichert.</p>';
  document.querySelectorAll('[data-payee-edit]').forEach(b=>b.onclick=()=>payeePresetDialog(payeePresetsCache.find(p=>p.id===Number(b.dataset.payeeEdit))));
  document.querySelectorAll('[data-payee-delete]').forEach(b=>b.onclick=async()=>{if(hpConfirm('Empfänger aus der Vorauswahl löschen? Bestehende Buchungen bleiben unverändert.')){await api('/api/payees/'+b.dataset.payeeDelete,{method:'DELETE'});await loadPayeePresets()}})
}
function payeePresetDialog(preset=null){openModal(`<h2>${preset?'Empfänger umbenennen':'Empfänger hinzufügen'}</h2><label>Name<input name="name" maxlength="200" required value="${esc(preset?.name||'')}"></label><p class="muted">Änderungen an dieser Liste verändern keine bestehenden Buchungen.</p>`,async f=>{await api(preset?'/api/payees/'+preset.id:'/api/payees',{method:preset?'PUT':'POST',body:JSON.stringify({name:f.get('name')})});await loadPayeePresets()})}
function bytesFmt(v){const n=Number(v||0),num=(value,digits)=>Number(value).toLocaleString(hpLocale(),{minimumFractionDigits:digits,maximumFractionDigits:digits});if(n<1024)return Number(n).toLocaleString(hpLocale())+' B';if(n<1024**2)return num(n/1024,1)+' KB';if(n<1024**3)return num(n/1024**2,1)+' MB';return num(n/1024**3,2)+' GB'}
async function loadBooksAdmin(){if(!$('bookList'))return;try{const rows=await api('/api/books');$('bookList').innerHTML=rows.map(b=>{const canManage=b.role==='owner'||currentMe?.system_role==='admin';return `<div class="book-row ${b.active?'active':''}"><span><b>${esc(b.name)}</b><small>${roleLabel(b.role)} · ${bytesFmt(b.size_bytes)}${b.active?' · aktuell':''}</small></span><div class="book-actions">${b.active?'<span class="badge">Aktiv</span>':`<button class="ghost" data-switch-book="${esc(b.id)}">Öffnen</button>`}${canManage?`<button class="ghost" data-rename-book="${esc(b.id)}" data-book-name="${esc(b.name)}">Umbenennen</button>${!b.active?`<button class="ghost danger-outline" data-delete-book="${esc(b.id)}" data-book-name="${esc(b.name)}">Löschen</button>`:''}`:''}</div></div>`}).join('');document.querySelectorAll('[data-switch-book]').forEach(b=>b.onclick=async()=>{await api('/api/books/'+encodeURIComponent(b.dataset.switchBook)+'/switch',{method:'POST'});location.reload()});document.querySelectorAll('[data-rename-book]').forEach(b=>b.onclick=async()=>{const old=b.dataset.bookName,name=hpPrompt('Neuer Name des Haushaltsbuchs:',old);if(!name||name.trim()===old)return;try{await api('/api/books/'+encodeURIComponent(b.dataset.renameBook),{method:'PUT',body:JSON.stringify({name:name.trim()})});toast('Haushaltsbuch umbenannt');await loadBooksAdmin();await loadAuditTimeline(true)}catch(err){toast(err.message)}});document.querySelectorAll('[data-delete-book]').forEach(b=>b.onclick=async()=>{const name=b.dataset.bookName;if(!hpConfirm(`Haushaltsbuch „${name}“ mit eigener Datenbank und internen Backups endgültig löschen?`))return;const confirmation=hpPrompt(`Zur Bestätigung exakt den Namen eingeben:\n${name}`);if(confirmation!==name)return;try{await api('/api/books/'+encodeURIComponent(b.dataset.deleteBook),{method:'DELETE',body:JSON.stringify({confirmation})});toast('Haushaltsbuch gelöscht');await loadBooksAdmin();await loadAuditTimeline(true)}catch(err){toast(err.message)}})}catch(err){$('bookList').innerHTML='<p class="muted">'+esc(err.message)+'</p>'}}
$('createBook').onclick=async()=>{const name=$('newBookName').value.trim();if(!name)return;try{await api('/api/books',{method:'POST',body:JSON.stringify({name})});$('newBookName').value='';toast('Haushaltsbuch angelegt');loadBooksAdmin()}catch(err){toast(err.message)}};
async function loadStorage(){try{const d=await api('/api/admin/storage');$('dbSize').textContent=bytesFmt(d.database_bytes);$('dbTxCount').textContent=Number(d.transactions).toLocaleString(hpLocale());$('dbAttachmentSize').textContent=`${bytesFmt(d.attachments_bytes)} / ${bytesFmt(d.attachment_limit_bytes)}`}catch(err){toast(err.message)}}
function deleteModeUi(){const m=$('deleteTxMode').value;$('deleteTxFrom').closest('label').hidden=m==='all';$('deleteTxTo').closest('label').hidden=m!=='range'}
$('deleteTxMode').onchange=deleteModeUi;
$('reloadStorage').onclick=loadStorage;
$('previewDeleteTx').onclick=async()=>{try{const m=$('deleteTxMode').value,p=new URLSearchParams({mode:m});if(m!=='all'&&$('deleteTxFrom').value)p.set('from_date',$('deleteTxFrom').value);if(m==='range'&&$('deleteTxTo').value)p.set('to_date',$('deleteTxTo').value);const d=await api('/api/admin/transactions-delete-preview?'+p);$('deleteTxPreview').innerHTML=`<b>${d.count.toLocaleString(hpLocale())} Buchungen</b> · ${d.transfers} Transfers${d.from?` · ${esc(formatDateValue(d.from))} ${esc(hpText('bis'))} ${esc(formatDateValue(d.to))}`:''}`;}catch(err){$('deleteTxPreview').textContent=err.message}};
$('executeDeleteTx').onclick=async()=>{const mode=$('deleteTxMode').value;const body={mode,from_date:mode==='all'?null:($('deleteTxFrom').value||null),to_date:mode==='range'?($('deleteTxTo').value||null):null,confirmation:canonicalDeleteConfirmation($('deleteTxConfirm').value)};if(!hpConfirm('Diese Buchungen werden endgültig gelöscht. Fortfahren?'))return;try{const d=await api('/api/admin/transactions',{method:'DELETE',body:JSON.stringify(body)});toast(`${d.deleted} Buchungen gelöscht`);$('deleteTxConfirm').value='';await loadStorage();await loadTransactions(true);await loadDashboard()}catch(err){toast(err.message)}};

async function loadSettings(){const s=await api('/api/settings');const isOwner=currentMe?.role==='owner'||currentMe?.system_role==='admin';const isAdmin=currentMe?.system_role==='admin';const userCard=document.querySelector('.user-management-card');if(userCard)userCard.hidden=!isOwner;const createBookForm=document.querySelector('.books-admin-card .inline-form');if(createBookForm)createBookForm.hidden=!isAdmin;if($('deleteTxControls'))$('deleteTxControls').hidden=!isOwner;loadAuditTimeline(true);loadPayeePresets();loadBooksAdmin();loadStorage();deleteModeUi();$('autolock').value=s.autolock_minutes||'15';const enabled=s.investment_tracking==='true';$('investments').checked=enabled;$('navInvestments').hidden=!enabled;if($('themeMode'))$('themeMode').value=localStorage.getItem('hp_theme')||'system';loadUsers()}
$('saveAutolock').onclick=async()=>{await api('/api/settings/autolock_minutes',{method:'PUT',body:JSON.stringify({value:$('autolock').value})});toast('Autolock gespeichert')};
$('saveTheme').onclick=()=>{const mode=$('themeMode').value;localStorage.setItem('hp_theme',mode);applyTheme(mode);toast('Darstellung gespeichert')};
$('saveInvestments').onclick=async()=>{const enabled=$('investments').checked;await api('/api/settings/investment_tracking',{method:'PUT',body:JSON.stringify({value:enabled?'true':'false'})});$('navInvestments').hidden=!enabled;if(!enabled&&document.querySelector('.nav.active')?.dataset.view==='investments')switchView('dashboard');toast('Investment-Einstellung gespeichert')};
$('checkSecurity').onclick=async()=>{const s=await api('/api/security');$('securityInfo').textContent=JSON.stringify(s,null,2)};
$('backupBtn').onclick=async()=>{const password=$('backupPassword').value;if(password.length<12)return toast('Backup-Passwort zu kurz');const r=await api('/api/backup',{method:'POST',body:JSON.stringify({password})});const blob=await r.blob(),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='haushaltpro-backup.hpb';a.click();URL.revokeObjectURL(a.href);$('backupPassword').value=''};
$('restoreBtn').onclick=async()=>{const file=$('restoreFile').files[0];if(!file)return toast('Backup-Datei wählen');if(!hpConfirm('Die aktuelle Datenbank wird ersetzt. Fortfahren?'))return;const f=new FormData();f.append('file',file);f.append('backup_password',$('restoreBackupPassword').value);f.append('database_password',$('restoreDbPassword').value);await api('/api/restore',{method:'POST',body:f});hpAlert('Wiederherstellung erfolgreich. Bitte erneut anmelden.');location.reload()};
$('passwordBtn').onclick=async()=>{await api('/api/password',{method:'POST',body:JSON.stringify({current_password:$('oldPassword').value,new_password:$('newPassword').value})});$('oldPassword').value='';$('newPassword').value='';toast('Passwort und Datenbank-Key geändert')};
$('runFinanceCheck').onclick=async()=>{const r=await api('/api/finance-check',{method:'POST'});renderFinanceCheck(r);toast(r.ok?'Finanz-Check bestanden':'Finanz-Check mit Hinweisen/Fehlern beendet')};
$('runScenario').onclick=runWhatIf;$('newContract').onclick=()=>contractDialog();
$('rotateBackupBtn').onclick=async()=>{const r=await api('/api/backup/rotate',{method:'POST'});$('backupStatus').textContent=`Internes Backup geprüft/angelegt · ${Math.round(Number(r.storage_bytes||0)/1024/1024)} MB lokal belegt`;toast('Interner Snapshot erstellt; Aufbewahrungsregeln angewendet')};
$('verifyBackupBtn').onclick=async()=>{const r=await api('/api/backup/status');$('backupStatus').textContent=r.ok?'Letztes internes Backup erfolgreich geprüft':('Backup-Prüfung: '+(r.error||r.message||'fehlgeschlagen'));};
$('csvBtn').onclick=async()=>{const file=$('csvFile').files[0];if(!file)return toast('CSV-Datei wählen');const f=new FormData();f.append('file',file);if($('csvAccount').value)f.append('account_id',$('csvAccount').value);const r=await api('/api/import/csv',{method:'POST',body:f});$('csvResult').textContent=`${r.imported} importiert, ${r.duplicates} Duplikate, ${r.skipped} übersprungen`;await loadCommon()};
setDashboardMode();setPlanningMode();boot();

$('planningReload').onclick=loadPlanning;$('planningPeriod').onchange=loadPlanning;$('planningMonthName').onchange=loadPlanning;$('planningYear').onchange=loadPlanning;$('forecastHorizon').onchange=loadPlanning;

let planningResizeTimer;
window.addEventListener('resize',()=>{if(window.innerWidth>800)setMobileNav(false);clearTimeout(planningResizeTimer);planningResizeTimer=setTimeout(()=>{const v=$('view-planning');if(v&&!v.hidden)loadPlanning().catch(()=>{})},180)});


$('auditReload').onclick=()=>loadAuditTimeline(true);$('auditSearch').onkeydown=e=>{if(e.key==='Enter')loadAuditTimeline(true)};$('auditSearchBtn').onclick=()=>loadAuditTimeline(true);$('auditPageSize').onchange=()=>loadAuditTimeline(true);$('auditFirst').onclick=()=>{auditPage=1;loadAuditTimeline()};$('auditPrev').onclick=()=>{auditPage=Math.max(1,auditPage-1);loadAuditTimeline()};$('auditNext').onclick=()=>{auditPage=Math.min(auditPages,auditPage+1);loadAuditTimeline()};$('auditLast').onclick=()=>{auditPage=auditPages;loadAuditTimeline()};

$('newPayeePreset').onclick=()=>payeePresetDialog();

function refreshLocalizedMonthControls(){
  for(const [monthId,yearId] of MONTH_CONTROL_PAIRS){
    const current=ensureMonthControls(monthId,yearId,selectedMonth);
    setMonthControls(monthId,yearId,current);
  }
}


document.addEventListener('haushaltpro:i18n-ready',()=>{
  updateThemeToggle();
  if($('app')&&!$('app').hidden)refreshLocalizedMonthControls();
});

document.addEventListener('haushaltpro:language-changed',async()=>{
  updateThemeToggle();
  refreshLocalizedMonthControls();
  if(!$('app')||$('app').hidden)return;
  renderAccounts();
  const active=document.querySelector('.nav.active')?.dataset.view;
  try{
    if(active==='dashboard')await reloadDashboardByMode();
    else if(active==='accounts-page')await loadAccountManager();
    else if(active==='transactions'){await loadTransactions();await loadRecurring();}
    else if(active==='budgets')await loadBudgets();
    else if(active==='reports')await loadReports();
    else if(active==='planning')await loadPlanning();
    else if(active==='finance-check')await loadFinanceCheck();
    else if(active==='investments')await loadInvestments();
    else if(active==='settings')await loadSettings();
  }catch(err){console.warn('Language refresh failed',err)}
});
