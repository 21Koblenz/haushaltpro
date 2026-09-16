/* Native details/summary keeps keyboard, touch and screen-reader behaviour. */
function transactionCards(rows){
  const text=s=>esc(hpText(s));
  const pair=(label,value)=>`<div><dt>${text(label)}</dt><dd>${value}</dd></div>`;
  if(!rows.length)return `<p class="panel muted">${text('Keine Buchungen.')}</p>`;
  return rows.map(t=>{
    const recurring=t.recurring||t.recurring_transfer_id;
    const payee=t.transfer?(t.transfer_side==='out'?t.transfer_to_account_name:t.transfer_from_account_name):(t.payee||'—');
    const repeat=t.recurring?recurrenceLabel(t.recurring_frequency,t.recurring_interval_count):(recurring?hpText('Wiederkehrend'):'—');
    const status=t.status==='planned'?'Geplant':t.status==='cancelled'?'Storniert':'Gebucht';
    const writable=currentMe?.permissions?.includes('write')||['owner','editor'].includes(currentMe?.role);
    const fields=[
      pair(t.transfer?'Gegenkonto':'Empfänger',esc(payee)),
      pair('Kategorie',t.transfer?text('Interner Transfer'):esc(t.category_name?categoryDisplayName(t.category_name):'—')),
      pair('Status',text(status)),pair('Wiederholung',esc(repeat)),
      pair('Wertstellung',esc(formatDateValue(t.value_date))),
      pair('Tags',esc(t.tags?.join(' · ')||'—')),
      pair('Notiz',esc(t.note||'—'))
    ];
    if(t.recurring_due_date&&t.recurring_due_date!==t.booking_date)fields.push(pair('Ursprünglicher Termin',esc(formatDateValue(t.recurring_due_date))));
    if(t.fixed_cost)fields.push(pair('Fixkosten',text('Ja')));
    if(t.confidence)fields.push(pair('Prognose-Sicherheit',text(({fixed:'Fest',likely:'Wahrscheinlich',estimated:'Geschätzt'})[t.confidence]||t.confidence)));
    const splits=t.splits?.length?`<div class="tx-splits"><strong>${text('Teilbeträge')}</strong>${t.splits.map(s=>`<p>${esc(categoryDisplayName(categoriesCache.find(c=>c.id===s.category_id)?.name||'Nicht kategorisiert'))} · ${fmt(s.amount)}${s.note?' · '+esc(s.note):''}</p>`).join('')}</div>`:'';
    return `<details class="transaction-card" data-transaction-id="${t.id}">
      <summary class="tx-summary">
        <span class="tx-summary-name">${recurring?`<span class="recurring-mark" role="img" aria-label="${text('Wiederkehrend')}" title="${text('Wiederkehrend')}">↻</span>`:''}${t.transfer?'<span aria-hidden="true">↔</span> ':''}<b>${esc(t.name||t.recurring_name||hpText('Buchung'))}</b></span>
        <time class="tx-summary-date" datetime="${esc(t.booking_date)}">${esc(formatDateValue(t.booking_date))}</time>
        <span class="tx-summary-account">${esc(t.account_name)}</span>
        <strong class="tx-summary-amount amount ${t.amount<0?'neg':'pos'}">${fmt(t.amount)}</strong>
        <span class="tx-chevron" aria-hidden="true">⌄</span>
      </summary>
      <div class="tx-expanded"><dl class="tx-detail-grid">${fields.join('')}</dl>${splits}
        <div class="tx-card-actions">
          ${writable?`<button data-edit="${t.id}">${text(t.recurring?'Termin anpassen':'Bearbeiten')}</button><button class="ghost" data-cancel="${t.id}">${text('Storno')}</button>`:''}
          <button class="ghost" data-attach="${t.id}">${text('Belege')}</button>
          ${writable?`<button class="ghost danger-outline" data-delete="${t.id}">${text('Löschen')}</button>`:''}
        </div>
      </div>
    </details>`;
  }).join('');
}
