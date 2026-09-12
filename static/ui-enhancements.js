(() => {
  'use strict';

  const SIGNED_MONEY_NAMES = new Set(['opening_balance', 'actual_balance']);

  function normalizeSignedMoneyInput(raw) {
    let value = String(raw ?? '').trim().replace(/\s/g, '').replace(/[−–—]/g, '-');
    if (!value) return '0';

    // Accept German decimal comma and common pasted values such as -1.234,56.
    if (value.includes(',') && value.includes('.')) {
      if (value.lastIndexOf(',') > value.lastIndexOf('.')) {
        value = value.replace(/\./g, '').replace(',', '.');
      } else {
        value = value.replace(/,/g, '');
      }
    } else if (value.includes(',')) {
      value = value.replace(',', '.');
    }

    if (!/^[+-]?\d+(?:\.\d{1,2})?$/.test(value)) {
      throw new Error('Ungültiger Geldbetrag. Beispiel: -1234,56');
    }
    return value.replace(/^\+/, '');
  }

  function addSignToggle(input) {
    if (!input || input.dataset.signedMoney === '1' || !SIGNED_MONEY_NAMES.has(input.name)) return;
    input.dataset.signedMoney = '1';
    input.type = 'text';
    input.inputMode = 'decimal';
    input.autocomplete = 'off';

    const wrap = document.createElement('div');
    wrap.className = 'signed-money-input';
    input.parentNode.insertBefore(wrap, input);

    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'ghost signed-money-toggle';
    toggle.textContent = '±';
    toggle.title = 'Vorzeichen wechseln';
    toggle.setAttribute('aria-label', 'Vorzeichen wechseln');
    toggle.addEventListener('click', () => {
      const current = String(input.value || '').trim();
      input.value = current.startsWith('-') ? current.slice(1) : '-' + current;
      input.focus();
      try { input.setSelectionRange(input.value.length, input.value.length); } catch (_) {}
    });

    wrap.append(toggle, input);

    if (input.name === 'opening_balance' && !wrap.nextElementSibling?.classList.contains('signed-money-help')) {
      const help = document.createElement('small');
      help.className = 'signed-money-help';
      help.textContent = 'Guthaben positiv, Soll/Dispo negativ. Beispiel: -1234,56 €.';
      wrap.after(help);
    }
  }

  function enhanceSignedMoneyInputs(root = document) {
    root.querySelectorAll?.('input[name="opening_balance"], input[name="actual_balance"]').forEach(addSignToggle);
  }

  const modalContent = document.getElementById('modalContent');
  const modalForm = document.getElementById('modalForm');

  if (modalContent) {
    enhanceSignedMoneyInputs(modalContent);
    new MutationObserver(() => enhanceSignedMoneyInputs(modalContent)).observe(modalContent, {
      childList: true,
      subtree: true,
    });
  }

  if (modalForm) {
    // Capture phase runs before HaushaltPro's dynamically assigned form handler.
    modalForm.addEventListener('submit', (event) => {
      try {
        modalForm.querySelectorAll('input[data-signed-money="1"]').forEach((input) => {
          input.value = normalizeSignedMoneyInput(input.value);
        });
      } catch (error) {
        event.preventDefault();
        event.stopImmediatePropagation();
        const toast = document.getElementById('toast');
        if (toast) {
          toast.textContent = error.message;
          toast.classList.add('show');
          window.setTimeout(() => toast.classList.remove('show'), 3000);
        }
      }
    }, true);
  }

  // Export only for deterministic regression tests/debugging; no network use.
  window.HaushaltProSignedMoney = Object.freeze({ normalize: normalizeSignedMoneyInput });
})();
