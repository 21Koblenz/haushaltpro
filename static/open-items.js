const openItemText=(de,en)=>hpLang()==='en'?en:de;
const openItemLabel=state=>hpText(({open:'Offen',partial:'Teilweise bezahlt',paid:'Bezahlt',cancelled:'Storniert'})[state]||state);
let openItemsPage=1,openItemsPages=1,openItemsRows=[],openItemsLoad=0;
const canEditPayments=()=>currentMe?.permissions?.includes('write')||['owner','editor'].includes(currentMe?.role);
function localToday(){const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`}
async function loadOpenItems(reset=false){
  if(reset)openItemsPage=1;
  const load=++openItemsLoad,book=currentMe?.book?.id;
  $('newOpenItem').hidden=!canEditPayments();
  $('openItemsList').textContent=openItemText('Laden …','Loading …');
  const params=new URLSearchParams({state:$('openItemState').value,q:$('openItemSearch').value.trim(),page:String(openItemsPage)});
  if($('openItemKind').value)params.set('kind',$('openItemKind').value);
  try{
    const result=await api('/api/open-items?'+params);
    if(load!==openItemsLoad||currentMe?.book?.id!==book)return;
    openItemsPage=result.page;openItemsPages=result.pages;openItemsRows=result.items;
    $('openPayable').textContent=fmt(result.totals.payable);
    $('openReceivable').textContent=fmt(result.totals.receivable);
    $('openOverdue').textContent=String(result.totals.overdue);
    $('openItemPageInfo').textContent=openItemText(`Seite ${result.page} / ${result.pages} · ${result.total} Posten`,`Page ${result.page} / ${result.pages} · ${result.total} items`);
    $('openItemPrev').disabled=result.page<=1;$('openItemNext').disabled=result.page>=result.pages;
    $('openItemsList').innerHTML=result.items.map(item=>`<details class="open-item-card ${item.overdue?'is-overdue':''}" data-open-item="${item.id}">
      <summary><span class="open-item-title"><b>${esc(item.name)}</b><small>${esc(item.payee)} · ${esc(item.kind==='payable'?openItemText('Verbindlichkeit','Payable'):openItemText('Forderung','Receivable'))}</small></span>
      <span class="open-item-balance"><strong>${fmt(item.remaining)}</strong><small>${esc(openItemText('Restbetrag','Remaining'))}</small></span>
      <span class="open-item-meta">${esc(openItemLabel(item.status))}${item.overdue?' · '+esc(openItemText('Überfällig','Overdue')):''}${item.due_date?' · '+esc(openItemText('Fällig','Due'))+' '+esc(formatDateValue(item.due_date)):''}</span><span class="tx-chevron" aria-hidden="true">⌄</span></summary>
      <div class="open-item-expanded"><p>${esc(openItemText('Gesamt','Total'))}: <b>${fmt(item.amount)}</b> · ${esc(openItemText('Bezahlt','Paid'))}: <b>${fmt(item.paid)}</b></p>
      ${item.note?`<p class="payment-note">${esc(item.note)}</p>`:''}
      <div class="tx-card-actions">${canEditPayments()?`${!item.cancelled&&item.remaining>0?`<button data-pay-item="${item.id}">${esc(openItemText('Zahlung erfassen','Record payment'))}</button>`:''}<button class="ghost" data-edit-item="${item.id}">${esc(hpText('Bearbeiten'))}</button>`:''}</div>
      <h3>${esc(openItemText('Zugeordnete Zahlungen','Linked payments'))}</h3><div data-payments-for="${item.id}" aria-live="polite"></div></div></details>`).join('')||`<p class="panel muted">${esc(openItemText('Keine passenden Posten.','No matching items.'))}</p>`;
    $('openItemsList').querySelectorAll('[data-edit-item]').forEach(b=>b.onclick=()=>openItemDialog(openItemsRows.find(x=>x.id===Number(b.dataset.editItem))));
    $('openItemsList').querySelectorAll('[data-pay-item]').forEach(b=>b.onclick=()=>paymentDialog(Number(b.dataset.payItem)).catch(e=>toast(e.message)));
    $('openItemsList').querySelectorAll('[data-open-item]').forEach(d=>d.addEventListener('toggle',()=>{if(d.open)loadItemPayments(Number(d.dataset.openItem))}));
  }catch(err){if(load===openItemsLoad){$('openItemsList').textContent=err.message;toast(err.message)}}
}
async function loadItemPayments(id){
  const container=document.querySelector(`[data-payments-for="${id}"]`);if(!container)return;
  container.textContent=openItemText('Laden …','Loading …');
  try{
    const item=await api('/api/open-items/'+id);
    if(!container.isConnected)return;
    container.innerHTML=item.payments.map(p=>`<div class="linked-payment"><span><b>${esc(p.name)}</b><small>${esc(formatDateValue(p.booking_date))} · ${esc(p.account_name)} · #${p.transaction_id}</small></span><strong>${fmt(p.amount)}</strong>${canEditPayments()?`<button type="button" class="ghost" data-unlink-payment="${p.id}">${esc(openItemText('Zuordnung lösen','Unlink'))}</button>`:''}</div>`).join('')||`<p class="muted">${esc(openItemText('Noch keine Zahlungen zugeordnet.','No payments linked yet.'))}</p>`;
    container.querySelectorAll('[data-unlink-payment]').forEach(b=>b.onclick=async()=>{
      if(!hpConfirm(openItemText('Zuordnung lösen? Die Kontobuchung bleibt erhalten; der Restbetrag steigt entsprechend.','Unlink payment? The account booking remains and the outstanding amount increases.')))return;
      b.disabled=true;
      try{await api('/api/open-items/'+id+'/payments/'+b.dataset.unlinkPayment,{method:'DELETE'});await loadOpenItems()}
      catch(err){b.disabled=false;toast(err.message)}
    });
  }catch(err){container.textContent=err.message}
}
function openItemDialog(item=null){
  const t=(de,en)=>esc(openItemText(de,en));
  openModal(`<h2>${t(item?'Posten bearbeiten':'Offenen Posten anlegen',item?'Edit item':'Create open item')}</h2>
    <label>${t('Art','Type')}<select name="kind"><option value="payable">${t('Verbindlichkeit – ich muss bezahlen','Payable – I owe money')}</option><option value="receivable" ${item?.kind==='receivable'?'selected':''}>${t('Forderung – ich bekomme Geld','Receivable – money owed to me')}</option></select></label>
    <label>${t('Bezeichnung','Title')}<input name="name" maxlength="160" required value="${esc(item?.name||'')}"></label>
    <label>${t('Empfänger / Gegenpartei','Payee / counterparty')}<input name="payee" maxlength="200" required value="${esc(item?.payee||'')}"></label>
    <label>${t('Ursprünglicher Gesamtbetrag EUR','Original total EUR')}<input name="amount" type="number" inputmode="decimal" min="0.01" max="999999999999.99" step="0.01" required value="${item?.amount??''}"></label>
    <label>${t('Fälligkeit (optional)','Due date (optional)')}<input name="due_date" type="date" value="${item?.due_date||''}"></label>
    <label>${t('Notiz','Note')}<textarea name="note" maxlength="1000">${esc(item?.note||'')}</textarea></label>
    ${item?`<label class="check"><input name="cancelled" type="checkbox" ${item.cancelled?'checked':''}> ${t('Posten stornieren','Cancel item')}</label><small>${t('Bereits gebuchte Zahlungen bleiben erhalten. Häkchen entfernen reaktiviert den Posten.','Existing payments remain. Clear the checkbox to reactivate the item.')}</small>`:''}
    <p class="muted">${t('Der Posten allein verändert keinen Kontostand und keine Prognose. Zahlungen werden über Kontobuchungen erfasst.','The item itself does not change balances or forecasts. Payments are recorded through account bookings.')}</p>`,
    async f=>{
      const body={kind:f.get('kind'),name:f.get('name'),payee:f.get('payee'),amount:String(f.get('amount')),due_date:f.get('due_date')||null,note:f.get('note')||null,cancelled:f.get('cancelled')==='on'};
      const result=await api(item?'/api/open-items/'+item.id:'/api/open-items',{method:item?'PUT':'POST',body:JSON.stringify(body)});
      if(result.offline_queued)return;await loadOpenItems();
    });
}
async function paymentDialog(id){
  const item=await api('/api/open-items/'+id);
  if(item.cancelled||item.remaining<=0)return toast(openItemText('Der Posten ist bereits erledigt.','This item is already settled.'));
  const t=(de,en)=>esc(openItemText(de,en));
  const categories=categoriesCache.filter(c=>item.kind==='receivable'?c.direction==='income':c.direction!=='income');
  openModal(`<h2>${t('Zahlung erfassen','Record payment')}</h2><p><b>${esc(item.name)}</b> · ${t('Offen','Outstanding')}: ${fmt(item.remaining)}</p>
    <label>${t('Zahlung','Payment')}<select id="paymentMode" name="mode"><option value="link">${t('Vorhandene Buchung zuordnen','Link existing booking')}</option><option value="new">${t('Neue Kontobuchung erstellen','Create account booking')}</option></select></label>
    <div id="paymentLinkFields"><label>${t('Buchung suchen','Find booking')}<input id="paymentSearch" placeholder="${t('Name, Empfänger, Konto oder Notiz','Name, payee, account or note')}"></label><div class="payment-search-actions"><button type="button" class="ghost" id="paymentSearchBtn">${t('Suchen','Search')}</button><button type="button" class="ghost" id="paymentMore" hidden>${t('Weitere laden','Load more')}</button></div>
      <label>${t('Buchung auswählen','Select booking')}<select id="paymentCandidate" name="transaction_id" required><option value="">${t('Laden …','Loading …')}</option></select></label><p class="muted" id="paymentCandidateHint" aria-live="polite"></p></div>
    <div id="paymentNewFields" hidden>
      <label>${t('Konto','Account')}<select name="account_id" required disabled>${accountOptions()}</select></label>
      <label>${t('Zahlungsdatum','Payment date')}<input name="booking_date" type="date" max="${localToday()}" value="${localToday()}" required disabled></label>
      <label>${t('Kategorie','Category')}<select name="category_id" required disabled><option value="">${t('Kategorie wählen …','Choose category …')}</option>${categories.map(c=>`<option value="${c.id}">${esc(categoryDisplayName(c.name))}</option>`).join('')}</select></label>
      <label>${t('Notiz zur Buchung','Booking note')}<input name="note" maxlength="1000" disabled></label>
    </div>
    <label>${t('Zugeordneter Betrag EUR','Allocated amount EUR')}<input id="paymentAmount" name="amount" type="number" inputmode="decimal" min="0.01" max="${item.remaining}" step="0.01" required value="${Number(item.remaining).toFixed(2)}"></label>
    <p class="muted">${t('Bei Teilzahlungen nur den gezahlten Betrag eintragen. Beim Zuordnen entsteht keine zusätzliche Kontobuchung.','For partial payments enter only the amount paid. Linking does not create another account booking.')}</p>`,
    async f=>{
      const body={amount:String(f.get('amount'))};
      if(f.get('mode')==='link')body.transaction_id=Number(f.get('transaction_id'));
      else Object.assign(body,{account_id:Number(f.get('account_id')),booking_date:f.get('booking_date'),category_id:Number(f.get('category_id')),note:f.get('note')||null});
      const result=await api('/api/open-items/'+id+'/payments',{method:'POST',body:JSON.stringify(body)});
      if(result.offline_queued)return;
      await loadOpenItems();await loadTransactions();
    });
  const mode=$('paymentMode'),select=$('paymentCandidate'),hint=$('paymentCandidateHint'),more=$('paymentMore');
  let candidates=[],candidatePage=1,searchRun=0;
  async function search(append=false){
    const run=++searchRun,query=$('paymentSearch').value.trim();
    if(!append){candidatePage=1;candidates=[];select.innerHTML='<option value="">'+t('Laden …','Loading …')+'</option>'}
    const requestedPage=append?candidatePage+1:1;
    more.disabled=true;
    try{
      const result=await api('/api/open-items/'+id+'/candidates?'+new URLSearchParams({q:query,page:String(requestedPage)}));
      if(run!==searchRun||!select.isConnected)return;
      candidatePage=requestedPage;
      const previous=select.value;candidates.push(...result.items);
      select.innerHTML='<option value="">'+t('Buchung wählen …','Choose booking …')+'</option>'+candidates.map(c=>`<option value="${c.id}">${esc(formatDateValue(c.booking_date)+' · '+c.name+' · '+c.account_name+' · '+fmt(c.available)+' '+openItemText('frei','available'))}</option>`).join('');
      if(append)select.value=previous;
      more.hidden=!result.has_more;more.disabled=false;
      hint.textContent=candidates.length?openItemText('Nur bereits gebuchte Zahlungen mit passender Richtung und freiem Betrag.','Only posted payments with the matching direction and an unallocated amount.'):openItemText('Keine passende Buchung gefunden. Suche ändern oder eine neue Kontobuchung erstellen.','No matching booking. Change the search or create a new booking.');
    }catch(err){if(run===searchRun&&select.isConnected){hint.textContent=err.message;more.disabled=false}}
  }
  select.onchange=()=>{const c=candidates.find(x=>x.id===Number(select.value));if(c){$('paymentAmount').value=Math.min(item.remaining,c.available).toFixed(2);$('paymentAmount').max=String(Math.min(item.remaining,c.available))}};
  mode.onchange=()=>{
    const create=mode.value==='new';
    for(const [container,enabled] of [[$('paymentNewFields'),create],[$('paymentLinkFields'),!create]]){
      container.hidden=!enabled;container.querySelectorAll('input,select,button').forEach(e=>e.disabled=!enabled);
    }
    $('paymentAmount').max=String(item.remaining);if(!create)select.onchange();
  };
  $('paymentSearchBtn').onclick=()=>search();
  $('paymentSearch').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();search()}};
  more.onclick=()=>search(true);search();
}

function exportDialog(fixed=false){
  const t=(de,en)=>esc(openItemText(de,en));
  const period=$('txPeriod').value,year=Number($('txYear').value)||new Date().getFullYear(),month=monthValue('txMonthName','txYear');
  const start=period==='all'?'':period==='year'?year+'-01-01':month+'-01';
  const end=period==='all'?'':period==='year'?year+'-12-31':month+'-'+new Date(year,Number(month.slice(5,7)),0).getDate();
  openModal(`<h2>${t('CSV-Export','CSV export')}</h2>
    <label>${t('Auswertung','Report')}<select name="report" id="csvExportReport"><option value="transactions">${t('Buchungen','Bookings')}</option><option value="fixed" ${fixed?'selected':''}>${t('Fixkosten – Monats- und Jahresplan','Fixed costs – monthly and yearly plan')}</option></select></label>
    <div id="csvExportDates"><label>${t('Von (optional)','From (optional)')}<input type="date" name="from_date" value="${start}"></label><label>${t('Bis (optional)','To (optional)')}<input type="date" name="to_date" value="${end}"></label><label>${t('Status','Status')}<select name="status"><option value="all">${t('Gebucht und geplant','Posted and planned')}</option><option value="executed">${t('Nur gebucht','Posted only')}</option><option value="planned">${t('Nur geplant','Planned only')}</option></select></label><label>${t('Suchtext (optional)','Search text (optional)')}<input name="q" maxlength="100" value="${esc($('txSearch').value)}"></label></div>
    <div id="csvExportYear"><label>${t('Jahr','Year')}<input name="year" type="number" min="2000" max="2100" value="${fixed?($('planningYear').value||year):year}" required></label></div>
    <label>${t('Konto','Account')}<select name="account_id"><option value="">${t('Alle Konten','All accounts')}</option>${accountOptions($('txAccountFilter').value)}</select></label>
    <label>${t('Kategorie','Category')}<select name="category_id"><option value="">${t('Alle Kategorien','All categories')}</option>${categoriesCache.map(c=>`<option value="${c.id}">${esc(categoryDisplayName(c.name))}</option>`).join('')}</select></label>
    <p class="muted" id="csvExportHelp"></p>`,
    async f=>{
      const isFixed=f.get('report')==='fixed',params=new URLSearchParams();
      for(const key of isFixed?['year','account_id','category_id']:['from_date','to_date','account_id','category_id','status','q']){if(f.get(key))params.set(key,f.get(key))}
      const response=await api('/api/export/'+(isFixed?'fixed-costs.csv':'transactions.csv')+'?'+params);
      const blob=await response.blob(),url=URL.createObjectURL(blob),link=document.createElement('a');
      link.href=url;link.download=isFixed?'haushaltpro-fixkosten-plan-'+f.get('year')+'.csv':'haushaltpro-buchungen.csv';
      document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);
    },{refresh:false,success:openItemText('CSV exportiert','CSV exported')});
  $('modalSave').textContent=openItemText('Herunterladen','Download');
  const choose=$('csvExportReport');
  choose.onchange=()=>{
    const isFixed=choose.value==='fixed';
    for(const [container,enabled] of [[$('csvExportYear'),isFixed],[$('csvExportDates'),!isFixed]]){container.hidden=!enabled;container.querySelectorAll('input,select').forEach(e=>e.disabled=!enabled)}
    $('csvExportHelp').textContent=isFixed?openItemText('Planwerte Januar–Dezember nach Fälligkeit, einschließlich Einzeltermin-Verschiebungen. Jahreszahlungen stehen im fälligen Monat.','January–December plan by due date, including shifted occurrences. Annual payments appear in their due month.'):openItemText('Alle passenden Buchungen, unabhängig von der aktuellen Seite. Bei Splits eine Zeile je Teilbetrag; ein Kategorie-Filter exportiert nur passende Teilbeträge. Stornierte Buchungen sind ausgeschlossen.','All matching bookings, independent of the current page. Split bookings produce one row per part; a category filter exports only matching parts. Cancelled bookings are excluded.');
  };choose.onchange();
}
$('newOpenItem').onclick=()=>openItemDialog();
$('openItemReload').onclick=()=>loadOpenItems(true);
$('openItemKind').onchange=()=>loadOpenItems(true);$('openItemState').onchange=()=>loadOpenItems(true);
$('openItemSearch').onkeydown=e=>{if(e.key==='Enter')loadOpenItems(true)};
$('openItemPrev').onclick=()=>{openItemsPage=Math.max(1,openItemsPage-1);loadOpenItems()};
$('openItemNext').onclick=()=>{openItemsPage=Math.min(openItemsPages,openItemsPage+1);loadOpenItems()};
$('txExport').onclick=()=>exportDialog();$('fixedCostsExport').onclick=()=>exportDialog(true);
window.addEventListener('hp-offline-synced',()=>{if(document.querySelector('.nav.active')?.dataset.view==='open-items')loadOpenItems()});
