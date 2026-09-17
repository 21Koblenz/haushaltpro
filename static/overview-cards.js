/* Shared native disclosure cards for the account and recurring overviews. */
function canWriteOverview(){
  return currentMe?.permissions?.includes('write')||['owner','editor'].includes(currentMe?.role);
}
function accountCards(rows,{manage=false}={}){
  const text=s=>esc(hpText(s));
  if(!rows.length)return `<p class="muted">${text(manage?'Für diesen Monat gibt es noch kein aktives Konto.':'Noch keine Konten.')}</p>`;
  return rows.map(a=>{
    const cutoff=a.balance_cutoff||'';
    const now=new Date(),today=`${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;
    const currentLabel=cutoff===today?'Bis heute':'Bis Stichtag';
    const metric=(label,value,extra='')=>`<div><dt>${text(label)}${extra?`<small>${esc(extra)}</small>`:''}</dt><dd class="amount ${value<0?'neg':''}">${fmt(value)}</dd></div>`;
    return `<details class="account-disclosure" data-account-id="${a.id}">
      <summary class="account-summary">
        <span class="account-summary-name"><b>${esc(a.name)}</b>${a.type?`<small>${esc(accountTypeLabel(a.type))}</small>`:''}</span>
        <span class="account-summary-balances">
          <span class="account-summary-balance"><strong class="amount ${a.balance<0?'neg':''}">${fmt(a.balance)}</strong><small>${text(currentLabel)}${cutoff?' · '+esc(formatDateValue(cutoff)):''}</small></span>
          <span class="account-summary-balance account-summary-end"><strong class="amount ${a.month_end_balance<0?'neg':''}">${fmt(a.month_end_balance)}</strong><small>${text('Monatsende')}</small></span>
        </span>
        <span class="tx-chevron" aria-hidden="true">⌄</span>
      </summary>
      <div class="account-expanded">
        <dl class="account-balance-grid">
          ${metric('Monatsanfang',a.month_start_balance)}
          ${metric(currentLabel,a.balance,cutoff?formatDateValue(cutoff):'')}
          ${metric('Monatsende',a.month_end_balance)}
        </dl>
        ${manage?`<dl class="tx-detail-grid account-info">${a.start_date?`<div><dt>${text('Start')}</dt><dd>${esc(formatDateValue(a.start_date))}</dd></div>`:''}${a.iban?`<div><dt>IBAN</dt><dd>${esc(a.iban)}</dd></div>`:''}</dl>`:''}
        ${manage&&canWriteOverview()?`<div class="account-actions"><button data-aedit="${a.id}">${text('Kontodaten bearbeiten')}</button><button class="ghost" data-acorrect="${a.id}">${text('Monatsanfang korrigieren')}</button><button class="ghost" data-areconcile="${a.id}">${text('Kontostand abgleichen')}</button></div>`:''}
      </div>
    </details>`;
  }).join('');
}

function recurringCards(rows,transfers,accounts=accountsCache){
  const text=s=>esc(hpText(s));
  const pair=(label,value)=>`<div><dt>${text(label)}</dt><dd>${value}</dd></div>`;
  const amap=Object.fromEntries(accounts.map(a=>[a.id,a.name]));
  const writable=canWriteOverview();
  const cards=[...rows.map(r=>({r,transfer:false})),...transfers.map(r=>({r,transfer:true}))];
  if(!cards.length)return `<p class="panel muted">${text('Keine wiederkehrenden Buchungen.')}</p>`;
  return cards.map(({r,transfer})=>{
    const account=transfer?`${r.from_account_name} → ${r.to_account_name}`:(amap[r.account_id]||'—');
    const count=r.journal_count??r.executed_count;
    const fields=[
      pair('Nächster Termin',esc(formatDateValue(r.next_date))),
      pair('Intervall',esc(recurrenceLabel(r.frequency,r.interval_count))),
      pair('Ende',r.valid_until?esc(formatDateValue(r.valid_until)):text('Unbegrenzt')),
      pair('Start',esc(formatDateValue(r.first_date))),
      pair(transfer?'Transfer-Serie':'Serie',esc('#'+(r.series_id||r.id))),
      ...(!transfer?[pair('Empfänger',esc(r.payee||'—')),pair('Kategorie',esc(categoryDisplayName(categoriesCache.find(c=>c.id===r.category_id)?.name||'—')))]:[]),
      pair('Notiz',esc(r.note||'—'))
    ];
    if(count!=null)fields.push(pair(hpT('recurring.inJournal','in Buchungen'),esc(count)));
    if(r.future_change_from)fields.push(`<div class="recurring-future-change"><dt>${text('Änderung vorgemerkt ab')}</dt><dd>${esc(formatDateValue(r.future_change_from))}</dd></div>`);
    if(r.fixed_cost)fields.push(pair('Fixkosten',text('Ja')));
    return `<details class="transaction-card recurring-card" data-series-id="${transfer?'transfer-':''}${r.id}">
      <summary class="tx-summary">
        <span class="tx-summary-name"><span class="recurring-mark" role="img" aria-label="${text('Wiederkehrend')}">↻</span>${transfer?'<span aria-hidden="true">↔</span>':''}<b>${esc(r.name)}</b></span>
        <time class="tx-summary-date" datetime="${esc(r.next_date||'')}">${esc(formatDateValue(r.next_date))}</time>
        <span class="tx-summary-account">${esc(account)}</span>
        <strong class="tx-summary-amount amount ${transfer?'':r.amount<0?'neg':'pos'}">${fmt(r.amount)}</strong>
        <span class="tx-chevron" aria-hidden="true">⌄</span>
      </summary>
      <div class="tx-expanded"><dl class="tx-detail-grid">${fields.join('')}</dl>
        ${writable?`<div class="tx-card-actions">${transfer?
          `<button data-rtedit="${r.id}">${text('Serie bearbeiten')}</button><button class="ghost" data-rtstop="${r.id}">${text('Stoppen')}</button><button class="ghost danger-outline" data-rtdel="${r.id}">${text('Serie löschen')}</button>`:
          `<button data-redit="${r.id}">${text('Serie bearbeiten')}</button><button class="ghost" data-roverride="${r.id}">${text('Monat anpassen')}</button><button class="ghost" data-stop="${r.id}">${text('Stoppen')}</button><button class="ghost danger-outline" data-rdel="${r.id}">${text('Serie löschen')}</button>`}</div>`:''}
      </div>
    </details>`;
  }).join('');
}
