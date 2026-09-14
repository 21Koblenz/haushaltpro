(() => {
  'use strict';
  const SIGNED_MONEY_NAMES = new Set(['opening_balance', 'actual_balance']);
  const tr=(key,fallback)=>window.HaushaltProI18n?.t(key) || fallback;
  function normalizeSignedMoneyInput(raw) {
    let value = String(raw ?? '').trim().replace(/\s/g, '').replace(/[−–—]/g, '-');
    if (!value) return '0';
    if (value.includes(',') && value.includes('.')) {
      if (value.lastIndexOf(',') > value.lastIndexOf('.')) value = value.replace(/\./g, '').replace(',', '.');
      else value = value.replace(/,/g, '');
    } else if (value.includes(',')) value = value.replace(',', '.');
    if (!/^[+-]?\d+(?:\.\d{1,2})?$/.test(value)) throw new Error(tr('validation.invalidMoney','Ungültiger Geldbetrag. Beispiel: -1234,56'));
    return value.replace(/^\+/, '');
  }
  function addSignToggle(input) {
    if (!input || input.dataset.signedMoney === '1' || !SIGNED_MONEY_NAMES.has(input.name)) return;
    input.dataset.signedMoney = '1'; input.type = 'text'; input.inputMode = 'decimal'; input.autocomplete = 'off';
    const wrap = document.createElement('div'); wrap.className = 'signed-money-input'; input.parentNode.insertBefore(wrap, input);
    const toggle = document.createElement('button'); toggle.type='button'; toggle.className='ghost signed-money-toggle'; toggle.textContent='±';
    toggle.title=tr('common.toggleSign','Vorzeichen wechseln'); toggle.setAttribute('aria-label',toggle.title);
    toggle.addEventListener('click',()=>{const current=String(input.value||'').trim();input.value=current.startsWith('-')?current.slice(1):'-'+current;input.focus();try{input.setSelectionRange(input.value.length,input.value.length)}catch(_){}});
    wrap.append(toggle,input);
    if(input.name==='opening_balance'&&!wrap.nextElementSibling?.classList.contains('signed-money-help')){
      const help=document.createElement('small');help.className='signed-money-help';help.dataset.i18n='accounts.signedHelp';help.textContent=tr('accounts.signedHelp','Guthaben positiv, Soll/Dispo negativ. Beispiel: -1234,56 €.');wrap.after(help);
    }
  }
  function enhanceSignedMoneyInputs(root=document){root.querySelectorAll?.('input[name="opening_balance"], input[name="actual_balance"]').forEach(addSignToggle)}

  function payeePickerLabels(){
    const en=(window.HaushaltProI18n?.language?.()||localStorage.getItem('hp_lang')||'de')==='en';
    return en
      ?{choose:'Select saved payee …',custom:'or enter another payee',help:'Select a saved payee above or enter a new name below.'}
      :{choose:'Gespeicherten Empfänger auswählen …',custom:'oder anderen Empfänger eingeben',help:'Gespeicherten Empfänger oben auswählen oder unten einen neuen Namen eingeben.'};
  }
  function enhancePayeePicker(root=document){
    const input=root.querySelector?.('input[name="payee"][list="payeeSuggestions"]');
    if(!input||input.dataset.payeePicker==='1')return;
    input.dataset.payeePicker='1';
    const labels=payeePickerLabels();
    const listId=input.getAttribute('list');
    const datalist=listId?document.getElementById(listId):null;
    const values=[...new Set(Array.from(datalist?.querySelectorAll('option')||[]).map(o=>String(o.value||'').trim()).filter(Boolean))];
    input.removeAttribute('list');
    input.placeholder=labels.custom;
    if(!values.length)return;
    const select=document.createElement('select');
    select.className='payee-preset-select';
    select.dataset.payeePickerSelect='1';
    select.setAttribute('aria-label',labels.choose.replace(' …',''));
    const placeholder=document.createElement('option');
    placeholder.value='';placeholder.textContent=labels.choose;select.append(placeholder);
    values.forEach(value=>{const option=document.createElement('option');option.value=value;option.textContent=value;select.append(option)});
    if(values.includes(String(input.value||'')))select.value=String(input.value||'');
    select.addEventListener('change',()=>{
      if(select.value){
        input.value=select.value;
        input.dispatchEvent(new Event('input',{bubbles:true}));
        input.dispatchEvent(new Event('change',{bubbles:true}));
      }
      input.focus();
    });
    input.before(select);
    const help=document.createElement('small');
    help.className='muted payee-picker-help';help.textContent=labels.help;
    input.after(help);
  }

  const modalContent=document.getElementById('modalContent'),modalForm=document.getElementById('modalForm');
  if(modalContent){
    enhanceSignedMoneyInputs(modalContent);enhancePayeePicker(modalContent);
    new MutationObserver(()=>{enhanceSignedMoneyInputs(modalContent);enhancePayeePicker(modalContent)}).observe(modalContent,{childList:true,subtree:true});
  }
  if(modalForm)modalForm.addEventListener('submit',(event)=>{try{modalForm.querySelectorAll('input[data-signed-money="1"]').forEach(input=>input.value=normalizeSignedMoneyInput(input.value))}catch(error){event.preventDefault();event.stopImmediatePropagation();const toast=document.getElementById('toast');if(toast){toast.textContent=error.message;toast.classList.add('show');setTimeout(()=>toast.classList.remove('show'),3000)}}},true);
  window.HaushaltProSignedMoney=Object.freeze({normalize:normalizeSignedMoneyInput});

  const el=id=>document.getElementById(id);
  const isOwner=()=>{try{return currentMe?.role==='owner'||currentMe?.system_role==='admin'}catch(_){return false}};
  const isEditor=()=>{try{return currentMe?.role==='editor'}catch(_){return false}};
  const canRequestBook=()=>isOwner()||isEditor();

  function applySettingsRoleVisibility(){
    const owner=isOwner();
    const userCard=document.querySelector('.user-management-card');
    const maintenance=document.querySelector('.data-maintenance-card');
    const audit=document.querySelector('.settings-audit-card');
    if(userCard)userCard.hidden=!owner;
    if(maintenance)maintenance.hidden=!owner;
    if(audit)audit.hidden=!owner;
    const createForm=document.querySelector('.books-admin-card .inline-form');
    if(createForm)createForm.hidden=!canRequestBook();
    const booksCard=document.querySelector('.books-admin-card');
    if(booksCard){
      const text=booksCard.querySelector('.section-head .muted');
      if(text&&!owner)text.textContent=isEditor()
        ?'Du kannst ein neues Haushaltsbuch beantragen. Ein Eigentümer muss die Anfrage freigeben; als Bearbeiter kannst du Haushaltsbücher weder umbenennen noch löschen.'
        :'Du kannst freigegebene Haushaltsbücher öffnen. Änderungen an Haushaltsbüchern sind Eigentümern vorbehalten.';
    }
  }

  function guardOwnerLoader(name){
    const original=window[name];
    if(typeof original!=='function'||original.__hpRoleGuard)return;
    const guarded=async function(...args){if(!isOwner())return null;return original.apply(this,args)};
    guarded.__hpRoleGuard=true;
    window[name]=guarded;
  }
  ['loadAuditTimeline','loadStorage','loadUsers'].forEach(guardOwnerLoader);

  async function refreshIdentity(){
    try{
      const me=await api('/api/me');
      currentMe=me;
      if(typeof populateBookSwitcher==='function')populateBookSwitcher(me);
      applySettingsRoleVisibility();
      return me;
    }catch(_){return null}
  }

  function ensureBookRequestPanel(){
    const card=document.querySelector('.books-admin-card');
    if(!card)return null;
    let host=el('bookRequestPanel');
    if(!host){host=document.createElement('div');host.id='bookRequestPanel';host.className='book-request-panel';card.append(host)}
    return host;
  }

  async function renderBookRequests(){
    const host=ensureBookRequestPanel();
    if(!host)return;
    if(!canRequestBook()){host.hidden=true;return}
    try{
      const rows=await api('/api/book-requests');
      host.hidden=false;
      const owner=isOwner();
      const title=owner?'Offene Freigaben':'Meine offenen Anfragen';
      if(!rows.length){host.innerHTML=`<hr><h3>${title}</h3><p class="muted">Keine offenen Haushaltsbuch-Anfragen.</p>`;return}
      host.innerHTML=`<hr><h3>${title}</h3><div class="book-request-list">${rows.map(r=>`<div class="book-request-row"><span><b>${esc(r.name)}</b><small>${owner?`Beantragt von ${esc(r.requested_by_username||r.requested_by||'–')}`:'Wartet auf Freigabe durch einen Eigentümer'} · ${esc(formatDateTimeValue(r.created_at))}</small></span>${owner?`<span class="book-request-actions"><button type="button" data-book-approve="${esc(r.id)}">Freigeben</button><button type="button" class="ghost danger-outline" data-book-reject="${esc(r.id)}">Ablehnen</button></span>`:'<span class="badge">Ausstehend</span>'}</div>`).join('')}</div>`;
      host.querySelectorAll('[data-book-approve]').forEach(b=>b.onclick=async()=>{b.disabled=true;try{const r=await api('/api/book-requests/'+encodeURIComponent(b.dataset.bookApprove)+'/approve',{method:'POST'});toast(`Haushaltsbuch „${r.name||''}“ freigegeben`);await refreshIdentity();if(typeof loadBooksAdmin==='function')await loadBooksAdmin();await renderBookRequests()}catch(err){toast(err.message)}finally{b.disabled=false}});
      host.querySelectorAll('[data-book-reject]').forEach(b=>b.onclick=async()=>{if(!window.confirm('Diese Haushaltsbuch-Anfrage ablehnen?'))return;b.disabled=true;try{await api('/api/book-requests/'+encodeURIComponent(b.dataset.bookReject),{method:'DELETE'});toast('Anfrage abgelehnt');await renderBookRequests()}catch(err){toast(err.message)}finally{b.disabled=false}});
    }catch(err){
      host.hidden=true;
      if(isOwner())console.warn('Book requests unavailable',err);
    }
  }

  const createBookButton=el('createBook');
  if(createBookButton){
    createBookButton.onclick=async()=>{
      const input=el('newBookName'),name=String(input?.value||'').trim();
      if(!name)return;
      try{
        const result=await api('/api/books',{method:'POST',body:JSON.stringify({name})});
        if(input)input.value='';
        if(result.pending){toast('Anfrage gespeichert. Ein Eigentümer muss das neue Haushaltsbuch freigeben.');await renderBookRequests()}
        else{toast('Haushaltsbuch angelegt');await refreshIdentity();if(typeof loadBooksAdmin==='function')await loadBooksAdmin()}
      }catch(err){toast(err.message)}
    };
  }

  function installPasswordUX(){
    const button=el('passwordBtn'),oldInput=el('oldPassword'),newInput=el('newPassword');
    if(!button||!oldInput||!newInput||button.dataset.hpSelfPassword==='1')return;
    button.dataset.hpSelfPassword='1';
    const card=button.closest('.settings-card');
    const heading=card?.querySelector('h2');if(heading)heading.textContent='Eigenes Passwort ändern';
    let note=card?.querySelector('.self-password-note');
    if(!note&&card){note=document.createElement('p');note.className='muted self-password-note';note.textContent='Jeder Benutzer kann sein eigenes Passwort ändern – unabhängig von seiner Rolle im Haushaltsbuch.';heading?.after(note)}
    let confirm=el('newPasswordConfirm');
    if(!confirm){confirm=document.createElement('input');confirm.id='newPasswordConfirm';confirm.type='password';confirm.autocomplete='new-password';confirm.placeholder='Neues Passwort wiederholen';newInput.after(confirm)}
    button.textContent='Passwort ändern';
    button.onclick=async()=>{
      const current=oldInput.value,neu=newInput.value,repeat=confirm.value;
      if(neu.length<12){toast('Das neue Passwort muss mindestens 12 Zeichen lang sein.');return}
      if(neu!==repeat){toast('Die neuen Passwörter stimmen nicht überein.');return}
      try{
        await api('/api/password',{method:'POST',body:JSON.stringify({current_password:current,new_password:neu})});
        oldInput.value='';newInput.value='';confirm.value='';
        try{if(currentMe)currentMe.must_change_password=false}catch(_){}
        card?.classList.remove('password-required');
        card?.querySelector('.temporary-password-warning')?.remove();
        toast('Passwort erfolgreich geändert');
      }catch(err){toast(err.message)}
    };
  }

  function enforceTemporaryPassword(){
    installPasswordUX();
    let required=false;try{required=!!currentMe?.must_change_password}catch(_){}
    const button=el('passwordBtn'),card=button?.closest('.settings-card');
    if(!card)return;
    card.classList.toggle('password-required',required);
    let warning=card.querySelector('.temporary-password-warning');
    if(required&&!warning){warning=document.createElement('div');warning.className='temporary-password-warning';warning.textContent='Du verwendest noch ein temporäres Passwort. Bitte ändere es jetzt in ein eigenes Passwort.';card.prepend(warning)}
    if(!required&&warning)warning.remove();
    if(required&&typeof switchView==='function'){
      switchView('settings');
      setTimeout(()=>card.scrollIntoView({behavior:'smooth',block:'center'}),80);
    }
  }

  const originalLoadSettings=window.loadSettings;
  if(typeof originalLoadSettings==='function'){
    window.loadSettings=async function(...args){
      const result=await originalLoadSettings.apply(this,args);
      applySettingsRoleVisibility();
      installPasswordUX();
      await renderBookRequests();
      return result;
    };
  }

  const originalShowApp=window.showApp;
  if(typeof originalShowApp==='function'){
    window.showApp=function(me){const result=originalShowApp.apply(this,arguments);setTimeout(()=>{applySettingsRoleVisibility();installPasswordUX();enforceTemporaryPassword()},0);return result};
  }

  function transactionLabels(){
    const en=(window.HaushaltProI18n?.language?.()||localStorage.getItem('hp_lang'))==='en';
    return en?['Date','Name','Account','Payee','Category','Recurring','Amount','Actions']:['Datum','Name','Konto','Empfänger','Kategorie','Wiederholung','Betrag','Aktionen'];
  }
  function labelTransactionRows(){
    const body=el('txBody');if(!body)return;
    const labels=transactionLabels();
    body.querySelectorAll('tr').forEach(row=>row.querySelectorAll('td').forEach((cell,i)=>{cell.dataset.label=labels[i]||''}));
  }
  const txBody=el('txBody');
  if(txBody){labelTransactionRows();new MutationObserver(labelTransactionRows).observe(txBody,{childList:true,subtree:true})}

  const app=el('app');
  if(app)new MutationObserver(()=>{if(!app.hidden){applySettingsRoleVisibility();installPasswordUX();enforceTemporaryPassword();labelTransactionRows()}}).observe(app,{attributes:true,attributeFilter:['hidden']});
  setTimeout(()=>{applySettingsRoleVisibility();installPasswordUX();if(app&&!app.hidden)enforceTemporaryPassword();labelTransactionRows()},0);
})();
