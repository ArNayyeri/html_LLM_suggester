// content.js - Antigravity Web Recorder Content Script
(function () {
  if (window.hasRecorder) return;
  window.hasRecorder = true;

  let rightClickedElement = null;
  let lastRecordedValues = new Map(); // Track input values

  function isRecording(callback) {
    chrome.storage.local.get({ isRecording: false }, function (result) {
      callback(!!result.isRecording);
    });
  }

  function record(details) {
    isRecording(function (recording) {
      if (!recording) return;
      chrome.storage.local.get({ recordedEvents: [] }, function (result) {
        const events = result.recordedEvents || [];
        events.push(details);
        chrome.storage.local.set({ recordedEvents: events });
      });
    });
  }

  function getXPath(element) {
    if (!element) return '';
    if (element.id) {
      return `//*[@id="${element.id}"]`;
    }
    if (element === document.body) {
      return '/html/body';
    }
    let xpath = '';
    let current = element;
    while (current && current.nodeType === 1) {
      let tagName = current.tagName.toLowerCase();
      if (current === document.documentElement) {
        xpath = '/html' + xpath;
        break;
      }
      let index = 1;
      let sibling = current.previousElementSibling;
      while (sibling) {
        if (sibling.tagName.toLowerCase() === tagName) index++;
        sibling = sibling.previousElementSibling;
      }
      xpath = `/${tagName}[${index}]` + xpath;
      current = current.parentElement;
    }
    return xpath;
  }

  function getElementValue(el) {
    if (!el) return '';
    if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT') {
      return el.value || '';
    }
    return el.textContent.trim();
  }

  function recordEvent(e) {
    isRecording(function (recording) {
      if (!recording) return;
      
      const target = e.target;
      if (!target || target.closest('.llm-recorder-ui')) return; // Ignore extension UI

      const val = getElementValue(target);
      const details = {
        type: e.type,
        tag: target.tagName,
        id: target.id || '',
        name: target.name || '',
        class: target.className || '',
        value: val || null,
        time: Date.now(),
        url: window.location.href,
        xpath: target.id ? `//*[@id="${target.id}"]` : getXPath(target)
      };

      record(details);
    });
  }

  // Listen for user interactions
  document.addEventListener('click', recordEvent, true);
  
  // Track input typing
  document.addEventListener('input', function (e) {
    if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA')) {
      lastRecordedValues.set(e.target, e.target.value);
    }
  }, true);

  document.addEventListener('change', recordEvent, true);

  // Track form submissions
  document.addEventListener('submit', function (e) {
    isRecording(function (recording) {
      if (!recording) return;
      const target = e.target;
      const details = {
        type: 'submit',
        tag: target.tagName,
        id: target.id || '',
        name: target.name || '',
        class: target.className || '',
        time: Date.now(),
        url: window.location.href,
        xpath: target.id ? `//*[@id="${target.id}"]` : getXPath(target)
      };
      record(details);
    });
  }, true);

  // Track right-clicked element for verification commands
  document.addEventListener('contextmenu', function (e) {
    rightClickedElement = e.target;
  }, true);

  // Initial navigation
  function recordNavigation(type) {
    record({
      type: type,
      time: Date.now(),
      url: window.location.href
    });
  }

  window.addEventListener('popstate', () => recordNavigation('popstate'));
  window.addEventListener('hashchange', () => recordNavigation('hashchange'));

  // ---------------------------------------------------------------------------
  // Chrome Extension Messaging
  // ---------------------------------------------------------------------------

  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request && request.type === 'getPageSnapshot') {
      const html = document.documentElement.outerHTML;
      sendResponse({
        html: html,
        url: window.location.href,
        title: document.title
      });
      return true;
    }

    if (request && request.type === 'injectInputSuggestions') {
      injectInputSuggestionButtons(request.suggestions || []);
      sendResponse({ success: true });
      return true;
    }

    if (request && request.type === 'recordVerificationCommand') {
      const command = request.command;
      if (rightClickedElement) {
        recordVerificationCommand(command, rightClickedElement);
        sendResponse({ success: true, command: command });
      } else {
        sendResponse({ success: false, error: 'No element selected' });
      }
      return true;
    }
  });

  // ---------------------------------------------------------------------------
  // Suggestion Injection & In-Page Modal UI
  // ---------------------------------------------------------------------------

  function injectInputSuggestionButtons(suggestions) {
    // Remove existing suggestion buttons
    document.querySelectorAll('.input-suggestion-btn').forEach(b => b.remove());

    if (!Array.isArray(suggestions) || suggestions.length === 0) {
      console.log('No suggestions to inject.');
      return;
    }

    console.log(`Injecting ${suggestions.length} suggestion button(s)...`);

    suggestions.forEach((item, idx) => {
      // Find element in page by id or name
      let el = null;
      if (item.id) {
        el = document.getElementById(item.id);
      }
      if (!el && item.name) {
        el = document.querySelector(`[name="${item.name}"]`);
      }
      if (!el && item.id) {
        el = document.querySelector(`[id*="${item.id}"]`);
      }

      if (!el) {
        console.warn('Could not find element for suggestion:', item);
        return;
      }

      // Create '?' button next to the field
      const btn = document.createElement('button');
      btn.textContent = '?';
      btn.className = 'input-suggestion-btn llm-recorder-ui';
      btn.title = `هوش مصنوعی: مشاهده پیشنهادات تست برای ${item.name || item.id}`;
      btn.setAttribute('data-idx', idx);

      btn.style.cssText = `
        position: absolute !important;
        z-index: 999999 !important;
        width: 24px !important;
        height: 24px !important;
        min-width: 24px !important;
        border-radius: 50% !important;
        background: linear-gradient(135deg, #0d6efd, #0b5ed7) !important;
        color: #ffffff !important;
        border: 2px solid #ffffff !important;
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3) !important;
        font-family: Arial, sans-serif !important;
        font-size: 13px !important;
        font-weight: bold !important;
        line-height: 1 !important;
        cursor: pointer !important;
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        padding: 0 !important;
        margin: 0 !important;
        transition: transform 0.15s, background 0.2s !important;
      `;

      function positionButton() {
        if (!el || !document.contains(el)) {
          btn.remove();
          return;
        }
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0 || window.getComputedStyle(el).display === 'none') {
          btn.style.display = 'none';
          return;
        }
        btn.style.display = 'inline-flex';
        const top = rect.top + window.pageYOffset + Math.max(0, (rect.height - 24) / 2);
        const left = rect.right + window.pageXOffset + 6;
        btn.style.top = `${top}px`;
        btn.style.left = `${left}px`;
      }

      positionButton();
      window.addEventListener('scroll', positionButton, { passive: true });
      window.addEventListener('resize', positionButton, { passive: true });

      btn.onmouseenter = () => { btn.style.transform = 'scale(1.15)'; };
      btn.onmouseleave = () => { btn.style.transform = 'scale(1)'; };

      btn.onclick = (e) => {
        e.stopPropagation();
        e.preventDefault();
        openInPageModal(item, btn);
      };

      document.body.appendChild(btn);
    });
  }

  function openInPageModal(item, triggerBtn) {
    // Remove existing modal if any
    const existing = document.getElementById('llm-suggestion-modal-overlay');
    if (existing) existing.remove();

    const overlay = document.createElement('div');
    overlay.id = 'llm-suggestion-modal-overlay';
    overlay.className = 'llm-recorder-ui';
    overlay.style.cssText = `
      position: fixed !important;
      top: 0 !important;
      left: 0 !important;
      width: 100vw !important;
      height: 100vh !important;
      background: rgba(0, 0, 0, 0.5) !important;
      backdrop-filter: blur(2px) !important;
      z-index: 1000000 !important;
      display: flex !important;
      align-items: center !important;
      justify-content: center !important;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Vazirmatn", Tahoma, sans-serif !important;
      direction: rtl !important;
      text-align: right !important;
    `;

    const modal = document.createElement('div');
    modal.style.cssText = `
      background: #ffffff !important;
      width: 580px !important;
      max-width: 92vw !important;
      max-height: 88vh !important;
      overflow-y: auto !important;
      border-radius: 12px !important;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3) !important;
      padding: 22px !important;
      box-sizing: border-box !important;
      color: #212529 !important;
    `;

    const fieldTitle = item.name || item.id || 'فیلد ورودی';
    const fieldType = item.type || 'text';
    const rangeVal = item.range || '';
    const examplesVal = (item.examples || []).join('\n');
    const badExamplesVal = (item.bad_examples || []).join('\n');

    modal.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #dee2e6; padding-bottom: 10px; margin-bottom: 16px;">
        <div>
          <h3 style="margin: 0; font-size: 17px; color: #0d6efd; font-weight: bold;">پیشنهادات تست فیلد: <span style="color:#212529;">${fieldTitle}</span></h3>
          <small style="color: #6c757d; font-size: 12px;">نوع فیلد: ${fieldType}</small>
        </div>
        <button id="modal-close-x" style="background:none; border:none; font-size: 22px; cursor:pointer; color: #888;">&times;</button>
      </div>

      <div style="margin-bottom: 14px;">
        <label style="display: block; font-weight: bold; margin-bottom: 6px; font-size: 13px; color: #333;">قوانین اعتبارسنجی (محدوده فیلد):</label>
        <textarea id="modal-range" style="width: 100%; height: 60px; padding: 8px 10px; border: 1px solid #ced4da; border-radius: 6px; font-size: 13px; box-sizing: border-box; resize: vertical; direction: rtl;">${rangeVal}</textarea>
      </div>

      <div style="margin-bottom: 14px;">
        <label style="display: block; font-weight: bold; margin-bottom: 6px; font-size: 13px; color: #198754;">مثال‌های معتبر و صحیح (هر مورد در یک خط):</label>
        <textarea id="modal-examples" style="width: 100%; height: 100px; padding: 8px 10px; border: 1px solid #198754; border-radius: 6px; font-size: 13px; box-sizing: border-box; resize: vertical; direction: ltr; text-align: left;">${examplesVal}</textarea>
      </div>

      <div style="margin-bottom: 18px;">
        <label style="display: block; font-weight: bold; margin-bottom: 6px; font-size: 13px; color: #dc3545;">مثال‌های نامعتبر / تست منفی (هر مورد در یک خط):</label>
        <textarea id="modal-bad-examples" style="width: 100%; height: 90px; padding: 8px 10px; border: 1px solid #dc3545; border-radius: 6px; font-size: 13px; box-sizing: border-box; resize: vertical; background: #fff8f8; direction: ltr; text-align: left;">${badExamplesVal}</textarea>
      </div>

      <div id="modal-status-msg" style="margin-bottom: 12px; font-size: 13px; display: none;"></div>

      <div style="display: flex; justify-content: flex-end; gap: 10px;">
        <button id="modal-cancel-btn" style="padding: 8px 16px; border: 1px solid #ced4da; background: #f8f9fa; border-radius: 6px; cursor: pointer; font-size: 13px;">انصراف</button>
        <button id="modal-update-btn" style="padding: 8px 16px; border: none; background: #0d6efd; color: white; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: bold;">تولید مجدد با AI</button>
        <button id="modal-confirm-btn" style="padding: 8px 18px; border: none; background: #198754; color: white; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: bold;">تأیید و ذخیره</button>
      </div>
    `;

    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    function closeModal() {
      overlay.remove();
    }

    document.getElementById('modal-close-x').onclick = closeModal;
    document.getElementById('modal-cancel-btn').onclick = closeModal;
    overlay.onclick = (e) => { if (e.target === overlay) closeModal(); };

    // Confirm button: saves to server (/confirm_suggestion) and updates ? button state
    document.getElementById('modal-confirm-btn').onclick = function () {
      const confirmedRange = document.getElementById('modal-range').value.trim();
      const confirmedExamples = document.getElementById('modal-examples').value.split('\n').map(s => s.trim()).filter(Boolean);
      const confirmedBad = document.getElementById('modal-bad-examples').value.split('\n').map(s => s.trim()).filter(Boolean);

      const confirmBtn = document.getElementById('modal-confirm-btn');
      confirmBtn.disabled = true;
      confirmBtn.textContent = 'در حال ذخیره...';

      fetch('http://localhost:5000/confirm_suggestion', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          field: item.id || item.name,
          range: confirmedRange,
          examples: confirmedExamples,
          bad_examples: confirmedBad,
          url: window.location.href,
          time: Date.now()
        })
      })
      .then(res => res.json())
      .then(resData => {
        // Turn button green
        if (triggerBtn) {
          triggerBtn.style.background = 'linear-gradient(135deg, #198754, #146c43) !important';
          triggerBtn.title = 'تأیید شد ✓';
        }
        item.range = confirmedRange;
        item.examples = confirmedExamples;
        item.bad_examples = confirmedBad;
        closeModal();
      })
      .catch(err => {
        confirmBtn.disabled = false;
        confirmBtn.textContent = 'تأیید و ذخیره';
        const msg = document.getElementById('modal-status-msg');
        msg.style.display = 'block';
        msg.style.color = '#dc3545';
        msg.textContent = 'خطا در ارتباط با سرور پایتون: ' + err.message;
      });
    };

    // Update / Regenerate with AI button: calls /update_input_suggestion
    document.getElementById('modal-update-btn').onclick = function () {
      const updateBtn = document.getElementById('modal-update-btn');
      updateBtn.disabled = true;
      updateBtn.textContent = 'در حال پردازش با هوش مصنوعی...';

      const currentRange = document.getElementById('modal-range').value.trim();
      const currentExamples = document.getElementById('modal-examples').value.split('\n').map(s => s.trim()).filter(Boolean);
      const currentBad = document.getElementById('modal-bad-examples').value.split('\n').map(s => s.trim()).filter(Boolean);

      fetch('http://localhost:5000/update_input_suggestion', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          field: item.id || item.name,
          range: currentRange,
          examples: currentExamples,
          bad_examples: currentBad
        })
      })
      .then(res => res.json())
      .then(data => {
        updateBtn.disabled = false;
        updateBtn.textContent = 'تولید مجدد با AI';

        if (data.range) document.getElementById('modal-range').value = data.range;
        if (data.new_examples) document.getElementById('modal-examples').value = data.new_examples.join('\n');
        if (data.new_bad_examples) document.getElementById('modal-bad-examples').value = data.new_bad_examples.join('\n');

        const msg = document.getElementById('modal-status-msg');
        msg.style.display = 'block';
        msg.style.color = '#198754';
        msg.textContent = 'مثال‌ها با موفقیت توسط هوش مصنوعی به‌روزرسانی شدند!';
      })
      .catch(err => {
        updateBtn.disabled = false;
        updateBtn.textContent = 'تولید مجدد با AI';
        const msg = document.getElementById('modal-status-msg');
        msg.style.display = 'block';
        msg.style.color = '#dc3545';
        msg.textContent = 'خطا در ارتباط با هوش مصنوعی: ' + err.message;
      });
    };
  }

  // ---------------------------------------------------------------------------
  // Verification Commands Feedback
  // ---------------------------------------------------------------------------

  function recordVerificationCommand(command, element) {
    if (!element) return;
    const target = `xpath=${getXPath(element)}`;
    const value = getElementValue(element);
    const details = {
      type: 'verification_command',
      command: command,
      target: target,
      value: value,
      time: Date.now(),
      url: window.location.href,
      element_tag: element.tagName,
      element_id: element.id || '',
      xpath: getXPath(element)
    };
    record(details);

    // Visual feedback
    const toast = document.createElement('div');
    toast.className = 'llm-recorder-ui';
    toast.style.cssText = `
      position: fixed; bottom: 20px; left: 20px; background: #198754; color: white;
      padding: 10px 16px; border-radius: 8px; z-index: 1000000; font-family: sans-serif;
      font-size: 13px; box-shadow: 0 4px 12px rgba(0,0,0,0.25);
    `;
    toast.textContent = `دستور ${command} با موفقیت ثبت شد.`;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 2500);
  }

})();
