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
      btn.style.marginLeft = '4px';
      btn.style.padding = '0 4px';
      btn.style.fontSize = '10px';
      btn.style.verticalAlign = 'middle';
      btn.title = 'Show input info';
      btn.onclick = (e) => {
        e.stopPropagation();
        e.preventDefault();
        showEditModal(item, idx, suggestions);
      };
      el.parentNode.insertBefore(btn, el.nextSibling);
    });
  }

  function showEditModal(item, idx, suggestions) {
    // Remove old modal if any
    const oldModal = document.getElementById('input-suggestion-modal');
    if (oldModal) oldModal.remove();
    const modal = document.createElement('div');
    modal.id = 'input-suggestion-modal';
    modal.style.position = 'fixed';
    modal.style.top = '50%';
    modal.style.left = '50%';
    modal.style.transform = 'translate(-50%, -50%)';
    modal.style.background = '#fff';
    modal.style.border = '1px solid #888';
    modal.style.padding = '16px';
    modal.style.zIndex = 99999;
    modal.style.boxShadow = '0 2px 12px #0003';
    modal.innerHTML = `
      <div style="font-weight:bold;margin-bottom:8px;">Edit Range & Examples</div>
      <div><b>Field:</b> ${item.name || item.id || ''}</div>
      <div style="margin:8px 0;">
        <label>Range:</label><br>
        <input id="edit-range" type="text" value="${item.range || ''}" style="width:100%;margin-bottom:8px;" />
      </div>
      <div style="margin:8px 0;">
        <label>Examples (one per line):</label><br>
        <textarea id="edit-examples" style="width:100%;height:60px;">${(item.examples||[]).join('\n')}</textarea>
      </div>
      <div style="text-align:right;">
        <button id="edit-cancel">Cancel</button>
        <button id="edit-submit">Submit</button>
      </div>
    `;
    document.body.appendChild(modal);
    document.getElementById('edit-cancel').onclick = () => modal.remove();
    document.getElementById('edit-submit').onclick = () => {
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
        modal.remove();
        if (data && Array.isArray(data.new_examples) && data.new_examples.length > 0) {
          // Update the examples in the modal and in the HTML
          suggestions[idx].examples = data.new_examples;
          // Optionally, update the field's placeholder or title with new examples
          if (item.id && document.getElementById(item.id)) {
            document.getElementById(item.id).setAttribute('title', 'Examples: ' + data.new_examples.join(', '));
          } else if (item.name && document.querySelector(`[name="${item.name}"]`)) {
            document.querySelector(`[name="${item.name}"]`).setAttribute('title', 'Examples: ' + data.new_examples.join(', '));
          }
          alert('Updated! New examples:\n' + data.new_examples.join('\n'));
        } else {
          alert('Updated and sent to backend!');
        }
      }).catch(() => {
        modal.remove();
        alert('Failed to send to backend.');
      });
    };
  }

})();
