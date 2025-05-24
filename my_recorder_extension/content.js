(function () {
  if (window.hasRecorder) return;
  window.hasRecorder = true;

  function isRecording(callback) {
    chrome.storage.local.get({ isRecording: false }, function (result) {
      callback(result.isRecording);
    });
  }

  function record(details) {
    isRecording(function (recording) {
      if (!recording) return;
      chrome.storage.local.get({ recordedEvents: [] }, function (result) {
        const events = result.recordedEvents;
        events.push(details);
        chrome.storage.local.set({ recordedEvents: events });
      });
    });
  }

  // Store all snapshots in memory for this tab
  window._snapshots = [];
  let lastSnapshot = { html: '', css: '' };

  function getCurrentHTML() {
    let html = document.documentElement.outerHTML;
    // Remove script tags to avoid sending them
    html = html.replace(/<script[^>]*>([\s\S]*?)<\/script>/gi, '');
    // Remove style tags to avoid sending them
    html = html.replace(/<style[^>]*>([\s\S]*?)<\/style>/gi, '');
    return html;
  }

  function getCurrentCSS() {
    let css = '';
    for (let sheet of document.styleSheets) {
      try {
        for (let rule of sheet.cssRules) {
          css += rule.cssText + '\n';
        }
      } catch (e) {
        // Ignore cross-origin stylesheets
      }
    }
    return css;
  }

  // Add debug log before sending snapshot
  function sendSnapshotToPython(eventType, eventObj) {
    isRecording(function (recording) {
      if (!recording) return;
      const html = getCurrentHTML();
      const css = getCurrentCSS();
      if (html !== lastSnapshot.html || css !== lastSnapshot.css) {
        lastSnapshot = { html, css };
        if (eventObj) {
          // Use the provided event object
          var lastEvent = eventObj;
          // Debug log
          console.log('Sending snapshot (with current event):', {
            eventType,
            time: Date.now(),
            url: window.location.href,
            html,
            css,
            event: lastEvent
          });
          fetch('http://localhost:5000/snapshot', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              eventType: eventType,
              time: Date.now(),
              url: window.location.href,
              html: html,
              css: css,
              event: lastEvent
            })
          }).catch(error => {
            console.error('Failed to send snapshot:', error);
            chrome.storage.local.set({ serverError: true });
          });
        } else {
          // Fallback: get last event from storage (for navigation, etc.)
          chrome.storage.local.get({ recordedEvents: [] }, function (result) {
            const events = result.recordedEvents;
            const lastEvent = events.length > 0 ? events[events.length - 1] : null;
            console.log('Sending snapshot:', {
              eventType,
              time: Date.now(),
              url: window.location.href,
              html,
              css,
              event: lastEvent
            });
            fetch('http://localhost:5000/snapshot', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                eventType: eventType,
                time: Date.now(),
                url: window.location.href,
                html: html,
                css: css,
                event: lastEvent
              })
            }).catch(error => {
              console.error('Failed to send snapshot:', error);
              chrome.storage.local.set({ serverError: true });
            });
          });
        }
      }
    });
  }

  function recordEvent(e) {
    let xpath = '';
    if (!e.target.id) {
      xpath = getXPath(e.target);
    }
    const details = {
      type: e.type,
      tag: e.target.tagName,
      id: e.target.id,
      class: e.target.className,
      value: e.target.value || null,
      x: e.clientX || null,
      y: e.clientY || null,
      time: Date.now(),
      url: window.location.href,
      xpath: xpath || null,
    };
    record(details);
    sendSnapshotToPython(e.type, details);
  }

  function getXPath(element) {
    if (element.id) {
      return '//*[@id="' + element.id + '"]';
    }
    if (element === document.body) {
      return '/html/body';
    }
    var ix = 0;
    var siblings = element.parentNode ? element.parentNode.childNodes : [];
    for (var i = 0; i < siblings.length; i++) {
      var sibling = siblings[i];
      if (sibling === element) {
        var tagName = element.tagName ? element.tagName.toLowerCase() : '';
        return getXPath(element.parentNode) + '/' + tagName + '[' + (ix + 1) + ']';
      }
      if (sibling.nodeType === 1 && sibling.tagName === element.tagName) {
        ix++;
      }
    }
    return '';
  }

  // Record navigation
  function recordNavigation(type) {
    record({
      type: type,
      time: Date.now(),
      url: window.location.href,
    });
    sendSnapshotToPython(type);
  }

  // Only record clicks, change, and submit (not input)
  ['click', 'change'].forEach(function (eventType) {
    document.addEventListener(eventType, recordEvent, true);
  });

  // Record form submissions
  document.addEventListener('submit', function (e) {
    let xpath = '';
    if (!e.target.id) {
      xpath = getXPath(e.target);
    }
    record({
      type: 'submit',
      tag: e.target.tagName,
      id: e.target.id,
      class: e.target.className,
      time: Date.now(),
      url: window.location.href,
      xpath: xpath || null
    });
    sendSnapshotToPython('submit');
  }, true);

  // Record navigation events (but NOT DOMContentLoaded)
  window.addEventListener('popstate', function () { recordNavigation('popstate'); });
  window.addEventListener('hashchange', function () { recordNavigation('hashchange'); });

  // Only record pageload after all resources are loaded
  window.addEventListener('load', function () {
    recordNavigation('pageload');
  });

  // If the script loads after the page is already loaded, trigger manually
  if (document.readyState === 'complete') {
    recordNavigation('pageload');
  }

  // Add message listener for all snapshots
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request && request.type === 'getAllPageSnapshots') {
      sendResponse({ snapshots: window._snapshots });
    }
    if (request && request.type === 'getPageSnapshot') {
      console.log('Received getPageSnapshot request');
      const html = document.documentElement.outerHTML;
      let css = '';
      for (let sheet of document.styleSheets) {
        try {
          for (let rule of sheet.cssRules) {
            css += rule.cssText + '\n';
          }
        } catch (e) {
          // Ignore cross-origin stylesheets
        }
      }
      sendResponse({
        html,
        css,
        url: window.location.href,
        title: document.title
      });
    }
    if (request && request.type === 'injectInputSuggestions') {
      injectInputSuggestionButtons(request.suggestions);
    }
    return true;
  });
  function injectInputSuggestionButtons(suggestions) {
    // Remove old buttons if any
    document.querySelectorAll('.input-suggestion-btn').forEach(btn => btn.remove());
    suggestions.forEach((item, idx) => {
      let el = null;
      if (item.id && document.getElementById(item.id)) {
        el = document.getElementById(item.id);
      } else if (item.name && document.querySelector(`[name="${item.name}"]`)) {
        el = document.querySelector(`[name="${item.name}"]`);
      }
      if (!el) return;

      const btn = document.createElement('button');
      btn.textContent = '?';
      btn.className = 'input-suggestion-btn';
      btn.setAttribute('data-idx', idx);
      
      // Complete CSS isolation to prevent host page interference
      btn.style.cssText = `
        margin: 0 0 0 4px !important;
        padding: 2px 6px !important;
        font-size: 12px !important;
        font-family: Arial, sans-serif !important;
        font-weight: normal !important;
        line-height: 1 !important;
        vertical-align: middle !important;
        border: 1px solid #ccc !important;
        border-radius: 3px !important;
        background-color: #f0f0f0 !important;
        color: #333 !important;
        cursor: pointer !important;
        display: inline-block !important;
        text-decoration: none !important;
        text-align: center !important;
        white-space: nowrap !important;
        box-sizing: border-box !important;
        min-width: 20px !important;
        height: auto !important;
        outline: none !important;
        position: relative !important;
        z-index: 9999 !important;
        box-shadow: none !important;
        text-shadow: none !important;
        text-transform: none !important;
        letter-spacing: normal !important;
        word-spacing: normal !important;
        float: none !important;
        clear: none !important;
        opacity: 1 !important;
        visibility: visible !important;
        overflow: visible !important;
        transform: none !important;
        transition: background-color 0.2s ease !important;
      `;
      
      btn.title = 'Show input info';
        // Add hover effects with event listeners to ensure they work
      btn.addEventListener('mouseenter', function() {
        // Only change color on hover if no state is set
        if (!this.getAttribute('data-state')) {
          this.style.setProperty('background-color', '#e0e0e0', 'important');
        }
      });
      
      btn.addEventListener('mouseleave', function() {
        // Keep the current background color based on state
        const state = this.getAttribute('data-state');
        if (state === 'confirmed' || state === 'submitted') {
          // Keep green
          this.style.setProperty('background-color', '#44ff44', 'important');
          this.style.setProperty('color', 'white', 'important');
        } else if (state === 'cancelled' || state === 'failed') {
          // Keep red
          this.style.setProperty('background-color', '#ff4444', 'important');
          this.style.setProperty('color', 'white', 'important');
        } else {
          // Return to default
          this.style.setProperty('background-color', '#f0f0f0', 'important');
          this.style.setProperty('color', '#333', 'important');
        }
      });
        btn.onclick = (e) => {
        e.stopPropagation();
        e.preventDefault();
        
        // Record question mark button click event
        const questionMarkClickTime = Date.now();
        record({
          type: 'suggestion_question_mark_click',
          time: questionMarkClickTime,
          url: window.location.href,
          tag: 'BUTTON',
          id: `suggestion-btn-${idx}`,
          class: 'input-suggestion-btn',
          value: null,
          x: e.clientX || null,
          y: e.clientY || null,
          xpath: null,
          field_name: item.name || item.id || '',
          field_type: item.type || '',
          suggestion_index: idx
        });
        
        showEditModal(item, idx, suggestions, questionMarkClickTime);
      };
      
      el.parentNode.insertBefore(btn, el.nextSibling);
    });
  }  function showEditModal(item, idx, suggestions, questionMarkClickTime) {
    // Remove old modal if any
    const oldModal = document.getElementById('input-suggestion-modal');
    if (oldModal) oldModal.remove();
    
    // Record modal open event
    const modalOpenTime = Date.now();
    const modalOpenDuration = modalOpenTime - questionMarkClickTime;
    
    record({
      type: 'suggestion_modal_open',
      time: modalOpenTime,
      url: window.location.href,
      tag: 'DIV',
      id: 'input-suggestion-modal',
      class: 'extension-modal',
      value: null,
      x: null,
      y: null,
      xpath: null,
      field_name: item.name || item.id || '',
      field_type: item.type || '',
      suggestion_index: idx,
      open_delay_ms: modalOpenDuration
    });
    
    const modal = document.createElement('div');
    modal.id = 'input-suggestion-modal';
    
    // Complete CSS isolation for the modal
    modal.style.cssText = `
      position: fixed !important;
      top: 50% !important;
      left: 50% !important;
      transform: translate(-50%, -50%) !important;
      background: #fff !important;
      border: 2px solid #888 !important;
      padding: 20px !important;
      z-index: 999999 !important;
      box-shadow: 0 4px 20px rgba(0,0,0,0.3) !important;
      width: 500px !important;
      max-width: 90vw !important;
      max-height: 90vh !important;
      overflow-y: auto !important;
      font-family: Arial, sans-serif !important;
      font-size: 14px !important;
      line-height: 1.4 !important;
      color: #333 !important;
      border-radius: 8px !important;
      box-sizing: border-box !important;
      margin: 0 !important;
      text-align: left !important;
      direction: ltr !important;
    `;

    modal.innerHTML = `
      <div style="font-weight:bold;margin-bottom:12px;font-size:16px;color:#333;">Edit Description & Examples</div>
      <div style="margin-bottom:8px;"><b>Field:</b> ${item.name || item.id || ''}</div>
      <div style="margin:12px 0;">
        <label style="display:block;margin-bottom:4px;font-weight:bold;">Description:</label>
        <textarea id="edit-range" style="width:100%;height:80px;margin-bottom:8px;resize:vertical;direction:rtl;text-align:right;padding:8px;border:1px solid #ccc;border-radius:4px;font-family:Arial,sans-serif;font-size:13px;box-sizing:border-box;">${item.range || ''}</textarea>
      </div>
      <div style="margin:12px 0;">
        <label style="display:block;margin-bottom:4px;font-weight:bold;">Examples (one per line):</label>
        <textarea id="edit-examples" style="width:100%;height:80px;padding:8px;border:1px solid #ccc;border-radius:4px;font-family:Arial,sans-serif;font-size:13px;box-sizing:border-box;direction:ltr;text-align:left;">${(item.examples||[]).join('\n')}</textarea>
      </div>
      <div style="display:flex;justify-content:space-between;gap:10px;margin-top:20px;">
        <button id="edit-cancel" style="padding:8px 16px;border:1px solid #ddd;border-radius:4px;background:#f5f5f5;cursor:pointer;font-size:14px;min-width:80px;">Cancel</button>
        <button id="edit-confirm" style="padding:8px 16px;border:1px solid #28a745;border-radius:4px;background:#28a745;color:white;cursor:pointer;font-size:14px;min-width:80px;">Confirm</button>
        <button id="edit-submit" style="padding:8px 16px;border:1px solid #007bff;border-radius:4px;background:#007bff;color:white;cursor:pointer;font-size:14px;min-width:80px;">Submit</button>
      </div>
    `;

    document.body.appendChild(modal);
    
    // Get the button element to change its color
    const buttonElement = document.querySelector(`.input-suggestion-btn[data-idx="${idx}"]`);    document.getElementById('edit-cancel').onclick = () => {
      const cancelTime = Date.now();
      const modalDuration = cancelTime - modalOpenTime;
      
      // Record cancel event
      record({
        type: 'suggestion_modal_cancel',
        time: cancelTime,
        url: window.location.href,
        tag: 'BUTTON',
        id: 'edit-cancel',
        class: 'modal-button',
        value: null,
        x: null,
        y: null,
        xpath: null,
        field_name: item.name || item.id || '',
        field_type: item.type || '',
        suggestion_index: idx,
        modal_duration_ms: modalDuration
      });
      
      modal.remove();
      // Change button color to red when cancelled
      if (buttonElement) {
        buttonElement.style.setProperty('background-color', '#ff4444', 'important');
        buttonElement.style.setProperty('color', 'white', 'important');
        // Store state for hover effect
        buttonElement.setAttribute('data-state', 'cancelled');
      }
    };
    
    document.getElementById('edit-confirm').onclick = () => {
      const confirmTime = Date.now();
      const modalDuration = confirmTime - modalOpenTime;
      
      // Record confirm event
      record({
        type: 'suggestion_modal_confirm',
        time: confirmTime,
        url: window.location.href,
        tag: 'BUTTON',
        id: 'edit-confirm',
        class: 'modal-button',
        value: null,
        x: null,
        y: null,
        xpath: null,
        field_name: item.name || item.id || '',
        field_type: item.type || '',
        suggestion_index: idx,
        modal_duration_ms: modalDuration
      });
      
      modal.remove();
      // Change button color to green when confirmed
      if (buttonElement) {
        buttonElement.style.setProperty('background-color', '#44ff44', 'important');
        buttonElement.style.setProperty('color', 'white', 'important');
        // Store state for hover effect
        buttonElement.setAttribute('data-state', 'confirmed');
      }
    };    document.getElementById('edit-submit').onclick = () => {
      const submitStartTime = Date.now();
      const modalDuration = submitStartTime - modalOpenTime;
      
      // Record submit start event
      record({
        type: 'suggestion_modal_submit_start',
        time: submitStartTime,
        url: window.location.href,
        tag: 'BUTTON',
        id: 'edit-submit',
        class: 'modal-button',
        value: null,
        x: null,
        y: null,
        xpath: null,
        field_name: item.name || item.id || '',
        field_type: item.type || '',
        suggestion_index: idx,
        modal_duration_ms: modalDuration
      });
      
      const newRange = document.getElementById('edit-range').value;
      const newExamples = document.getElementById('edit-examples').value.split('\n').map(s=>s.trim()).filter(Boolean);
      // Update the suggestion in memory
      suggestions[idx].range = newRange;
      suggestions[idx].examples = newExamples;
      // Send to backend
      fetch('http://localhost:5000/update_input_suggestion', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          field: item.name || item.id,
          range: newRange,
          examples: newExamples
        })
      }).then(res => res.json())
      .then(data => {
        const submitEndTime = Date.now();
        const submitDuration = submitEndTime - submitStartTime;
        const totalModalDuration = submitEndTime - modalOpenTime;
        
        // Record submit success event
        record({
          type: 'suggestion_modal_submit_success',
          time: submitEndTime,
          url: window.location.href,
          tag: 'BUTTON',
          id: 'edit-submit',
          class: 'modal-button',
          value: null,
          x: null,
          y: null,
          xpath: null,
          field_name: item.name || item.id || '',
          field_type: item.type || '',
          suggestion_index: idx,
          submit_duration_ms: submitDuration,
          total_modal_duration_ms: totalModalDuration,
          server_response: data
        });
        
        modal.remove();
        // Change button color to green when submitted successfully
        if (buttonElement) {
          buttonElement.style.setProperty('background-color', '#44ff44', 'important');
          buttonElement.style.setProperty('color', 'white', 'important');
          // Store state for hover effect
          buttonElement.setAttribute('data-state', 'submitted');
        }
        
        if (data && Array.isArray(data.new_examples) && data.new_examples.length > 0) {
          // Update the examples in the modal and in the HTML
          suggestions[idx].examples = data.new_examples;
          
          // Update the range if the server generated one
          if (data.range) {
            suggestions[idx].range = data.range;
          }
          
          // Optionally, update the field's placeholder or title with new examples
          if (item.id && document.getElementById(item.id)) {
            document.getElementById(item.id).setAttribute('title', 'Examples: ' + data.new_examples.join(', '));
          } else if (item.name && document.querySelector(`[name="${item.name}"]`)) {
            document.querySelector(`[name="${item.name}"]`).setAttribute('title', 'Examples: ' + data.new_examples.join(', '));
          }
          
          // Show both the new range and examples in the alert
          const alertMessage = data.range ? 
            `Updated!\nDescription: ${data.range}\nNew examples:\n${data.new_examples.join('\n')}` :
            `Updated!\nNew examples:\n${data.new_examples.join('\n')}`;
          
          alert(alertMessage);        } else {
          alert('Updated and sent to backend!');
        }
      }).catch(() => {
        const submitFailTime = Date.now();
        const submitDuration = submitFailTime - submitStartTime;
        const totalModalDuration = submitFailTime - modalOpenTime;
        
        // Record submit failure event
        record({
          type: 'suggestion_modal_submit_failure',
          time: submitFailTime,
          url: window.location.href,
          tag: 'BUTTON',
          id: 'edit-submit',
          class: 'modal-button',
          value: null,
          x: null,
          y: null,
          xpath: null,
          field_name: item.name || item.id || '',
          field_type: item.type || '',
          suggestion_index: idx,
          submit_duration_ms: submitDuration,
          total_modal_duration_ms: totalModalDuration
        });
        
        modal.remove();
        // Change button color to red when submission fails
        if (buttonElement) {
          buttonElement.style.setProperty('background-color', '#ff4444', 'important');
          buttonElement.style.setProperty('color', 'white', 'important');
          // Store state for hover effect
          buttonElement.setAttribute('data-state', 'failed');
        }
        alert('Failed to send to backend.');
      });
    };
  }

})();
