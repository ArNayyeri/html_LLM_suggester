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
  });  function injectInputSuggestionButtons(suggestions) {
    // Save the current suggestions to chrome storage for access when handling popup window messages
    chrome.storage.local.set({ currentSuggestions: suggestions });
    
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
      });        btn.onclick = (e) => {
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
        
        // Many browsers block popups unless they're triggered directly by a user action
        // So we need to call showEditModal directly from the click event handler
        try {
          showEditModal(item, idx, suggestions, questionMarkClickTime);
        } catch (err) {
          console.error('Failed to open popup:', err);
          alert('Failed to open popup window. Please check if popup blocking is enabled.');
        }
      };
      
      el.parentNode.insertBefore(btn, el.nextSibling);
    });
  }  function showEditModal(item, idx, suggestions, questionMarkClickTime) {
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
    
    // Always get the most recent data from storage
    chrome.storage.local.get({ currentSuggestions: [] }, function(result) {
      const currentSuggestions = result.currentSuggestions || [];
      let currentItem = item;
      
      // Use the most up-to-date data if available
      if (currentSuggestions.length > idx) {
        const storedItem = currentSuggestions[idx];
        // Only update if we have the same field to avoid confusion
        if ((storedItem.id && storedItem.id === item.id) || 
            (storedItem.name && storedItem.name === item.name)) {
          currentItem = storedItem;
        }
      }
      
      // Create URL for the popup with data in query parameters
      const extensionURL = chrome.runtime.getURL('suggestion_popup.html');
      
      // Build URL with parameters
      const params = new URLSearchParams();
      params.append('id', currentItem.id || '');
      params.append('name', currentItem.name || '');
      params.append('type', currentItem.type || '');
      params.append('idx', idx.toString());
      params.append('timestamp', Date.now().toString()); // Add timestamp to prevent caching
      
      // Add the range and examples if available
      if (currentItem.range) {
        params.append('range', currentItem.range);
      }
      
      if (currentItem.examples && currentItem.examples.length > 0) {
        params.append('examples', JSON.stringify(currentItem.examples));
      }
      
      const popupURL = `${extensionURL}?${params.toString()}`;
      
      // Open popup window with specified size and position
      const popupWidth = 550;
      const popupHeight = 450;
      const left = (window.screen.width / 2) - (popupWidth / 2);
      const top = (window.screen.height / 2) - (popupHeight / 2);
        // Check for existing popup with the same name
      let popupWindow;
      try {
        // Use a different window name each time to prevent caching issues
        const uniqueWindowName = `edit_field_${idx}_${Date.now()}`;
        
        // First, try to close any existing window
        const existingWindow = window.open('', `edit_field_${idx}`);
        if (existingWindow && !existingWindow.closed) {
          existingWindow.close();
        }
        
        // Create the popup window
        popupWindow = window.open(
          popupURL, 
          uniqueWindowName, 
          `width=${popupWidth},height=${popupHeight},left=${left},top=${top},resizable=yes,scrollbars=yes,status=no,location=no,menubar=no,toolbar=no`
        );
      } catch (e) {
        console.error("Error with popup window:", e);
        
        // Create a new popup as fallback
        popupWindow = window.open(
          popupURL, 
          `edit_field_${idx}_${Math.random().toString(36).substring(2, 9)}`, 
          `width=${popupWidth},height=${popupHeight},left=${left},top=${top},resizable=yes,scrollbars=yes,status=no,location=no,menubar=no,toolbar=no`
        );
      }
      
      if (popupWindow) {
        popupWindow.focus();
      } else {
        alert('Popup window was blocked. Please allow popups for this website.');
      }
    });
    
    // Get the button element to change its color based on action from popup
    const buttonElement = document.querySelector(`.input-suggestion-btn[data-idx="${idx}"]`);// Add window message listener for messages from the popup window
    // Since we're using a global function, add a one-time setup if not already set
    if (!window.hasSetupMessageListener) {
      window.hasSetupMessageListener = true;
      
      window.addEventListener('message', function(event) {
        // Process messages from popup windows
        if (event.data && event.data.action) {
          const eventData = event.data;
          const itemInfo = eventData.itemInfo;
          
          if (!itemInfo) return;
          
          // Find the relevant suggestion
          let suggestion = null;
          let suggestionIdx = itemInfo.idx;
          let actualItem = null;
          
          // Try to find the actual suggestion item
          chrome.storage.local.get({ currentSuggestions: [] }, function(result) {
            const currentSuggestions = result.currentSuggestions || [];
            if (suggestionIdx < currentSuggestions.length) {
              suggestion = currentSuggestions[suggestionIdx];
              
              // Find the HTML element
              if (itemInfo.id) {
                actualItem = document.getElementById(itemInfo.id);
              } else if (itemInfo.name) {
                actualItem = document.querySelector(`[name="${itemInfo.name}"]`);
              }
              
              // Get the button element to change its color
              const buttonElement = document.querySelector(`.input-suggestion-btn[data-idx="${suggestionIdx}"]`);
              
              // Handle different actions
              switch (eventData.action) {
                case 'cancelEdit':
                  const cancelTime = eventData.time;
                  
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
                    field_name: itemInfo.name || '',
                    field_type: itemInfo.type || '',
                    suggestion_index: suggestionIdx
                  });
                  
                  // Change button color to red when cancelled
                  if (buttonElement) {
                    buttonElement.style.setProperty('background-color', '#ff4444', 'important');
                    buttonElement.style.setProperty('color', 'white', 'important');
                    // Store state for hover effect
                    buttonElement.setAttribute('data-state', 'cancelled');
                  }
                  break;
                  
                case 'confirmEdit':
                  const confirmTime = eventData.time;
                  
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
                    field_name: itemInfo.name || '',
                    field_type: itemInfo.type || '',
                    suggestion_index: suggestionIdx
                  });
                  
                  // Change button color to green when confirmed
                  if (buttonElement) {
                    buttonElement.style.setProperty('background-color', '#44ff44', 'important');
                    buttonElement.style.setProperty('color', 'white', 'important');
                    // Store state for hover effect
                    buttonElement.setAttribute('data-state', 'confirmed');
                  }
                  
                  // Send confirmation to Python backend
                  const confirmData = {
                    field: itemInfo.name || itemInfo.id,
                    time: confirmTime,
                    url: window.location.href,
                    suggestion_index: suggestionIdx,
                    suggestion: suggestion
                  };
                  
                  fetch('http://localhost:5000/confirm_suggestion', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(confirmData)
                  })
                  .then(res => res.json())
                  .then(data => {
                    console.log('Confirmation successfully sent to backend:', data);
                    
                    // Record the successful confirmation persistence
                    record({
                      type: 'suggestion_confirmation_saved',
                      time: Date.now(),
                      url: window.location.href,
                      field_name: itemInfo.name || '',
                      field_id: itemInfo.id || '',
                      suggestion_index: suggestionIdx,
                      server_response: data
                    });
                    
                    // Show success notification
                    try {
                      const notification = document.createElement('div');
                      notification.style.cssText = `
                        position: fixed;
                        bottom: 20px;
                        right: 20px;
                        background-color: #44ff44;
                        color: white;
                        padding: 10px 15px;
                        border-radius: 4px;
                        z-index: 10000;
                        box-shadow: 0 2px 5px rgba(0,0,0,0.2);
                      `;
                      notification.innerHTML = `
                        <div>
                          <strong>Confirmation saved!</strong>
                          <span style="margin-left: 10px; cursor: pointer; font-weight: bold;">ⓘ</span>
                        </div>
                      `;
                      
                      document.body.appendChild(notification);
                      
                      // Remove after 3 seconds
                      setTimeout(() => {
                        if (notification.parentNode) {
                          notification.parentNode.removeChild(notification);
                        }
                      }, 3000);
                    } catch (e) {
                      console.error('Error showing notification:', e);
                    }
                  })
                  .catch(error => {
                    console.error('Failed to send confirmation to backend:', error);
                    
                    // Record failure
                    record({
                      type: 'suggestion_confirmation_failed',
                      time: Date.now(),
                      url: window.location.href,
                      field_name: itemInfo.name || '',
                      field_id: itemInfo.id || '',
                      suggestion_index: suggestionIdx,
                      error: error.message
                    });
                    
                    // Store failed confirmation for retry later
                    chrome.storage.local.get({ failedConfirmations: [] }, function(result) {
                      const failedConfirmations = result.failedConfirmations || [];
                      failedConfirmations.push(confirmData);
                      chrome.storage.local.set({ failedConfirmations: failedConfirmations });
                    });
                  });
                  break;
                  
                case 'submitEdit':
                  const submitStartTime = eventData.time;
                  
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
                    field_name: itemInfo.name || '',
                    field_type: itemInfo.type || '',
                    suggestion_index: suggestionIdx
                  });
                  
                  // Get the values from the message
                  const newRange = eventData.data.range;
                  const newExamples = eventData.data.examples;
                  
                  // Update the suggestion in memory
                  currentSuggestions[suggestionIdx].range = newRange;
                  currentSuggestions[suggestionIdx].examples = newExamples;
                  chrome.storage.local.set({ currentSuggestions: currentSuggestions });
                  
                  // Send to backend
                  fetch('http://localhost:5000/update_input_suggestion', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                      field: itemInfo.name || itemInfo.id,
                      range: newRange,
                      examples: newExamples
                    })
                  }).then(res => res.json())
                  .then(data => {
                    const submitEndTime = Date.now();
                    const submitDuration = submitEndTime - submitStartTime;
                    
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
                      field_name: itemInfo.name || '',
                      field_type: itemInfo.type || '',
                      suggestion_index: suggestionIdx,
                      submit_duration_ms: submitDuration,
                      server_response: data
                    });
                    
                    // Change button color to green when submitted successfully
                    if (buttonElement) {
                      buttonElement.style.setProperty('background-color', '#44ff44', 'important');
                      buttonElement.style.setProperty('color', 'white', 'important');
                      // Store state for hover effect
                      buttonElement.setAttribute('data-state', 'submitted');
                    }
                      if (data && Array.isArray(data.new_examples) && data.new_examples.length > 0) {
                      // Update the examples in memory
                      currentSuggestions[suggestionIdx].examples = data.new_examples;
                      
                      // Update the range if the server generated one
                      if (data.range) {
                        currentSuggestions[suggestionIdx].range = data.range;
                      }
                        // Save updated suggestions and trigger update in any open popup windows
                      chrome.storage.local.set({ currentSuggestions: currentSuggestions }, function() {
                        // Notify any open popup windows to refresh their data
                      try {
                          // Store the updated suggestion with a timestamp to ensure freshness
                          currentSuggestions[suggestionIdx].lastUpdated = Date.now();
                          
                          // Try to update any open popup
                          const popupName = `edit_field_${suggestionIdx}`;
                          const existingPopup = window.open('', popupName);
                          
                          if (existingPopup && !existingPopup.closed) {
                            // Try to send a message to update the popup content
                            existingPopup.postMessage({
                              action: 'updateSuggestionData',
                              suggestion: currentSuggestions[suggestionIdx]
                            }, '*');
                          }
                        } catch (e) {
                          console.error("Error communicating with popup:", e);
                        }
                      });
                      
                      // Optionally, update the field's placeholder or title with new examples
                      if (actualItem) {
                        actualItem.setAttribute('title', 'Examples: ' + data.new_examples.join(', '));
                      }
                        // Show both the new range and examples in a notification
                      const alertMessage = data.range ? 
                        `Updated!\nDescription: ${data.range}\nNew examples:\n${data.new_examples.join('\n')}` :
                        `Updated!\nNew examples:\n${data.new_examples.join('\n')}`;
                      
                      // Create a non-intrusive notification instead of an alert
                      try {
                        const notification = document.createElement('div');
                        notification.style.cssText = `
                          position: fixed;
                          top: 20px;
                          right: 20px;
                          background: #28a745;
                          color: white;
                          padding: 15px 20px;
                          border-radius: 5px;
                          z-index: 999999;
                          box-shadow: 0 3px 10px rgba(0,0,0,0.2);
                          max-width: 300px;
                          font-family: Arial, sans-serif;
                          animation: fadeIn 0.3s ease-out;
                        `;
                        
                        notification.innerHTML = `
                          <div style="font-weight:bold;margin-bottom:5px;">Suggestion Updated</div>
                          <div style="font-size:12px;">${data.new_examples.length} examples received from server</div>
                          <div style="margin-top:10px;font-size:12px;text-align:center;">
                            <span style="cursor:pointer;text-decoration:underline;">View details</span>
                          </div>
                        `;
                        
                        // Add click event to show full details
                        notification.querySelector('span').onclick = function() {
                          alert(alertMessage);
                        };
                        
                        // Add to document
                        document.body.appendChild(notification);
                        
                        // Remove after 5 seconds
                        setTimeout(() => {
                          if (notification.parentNode) {
                            notification.parentNode.removeChild(notification);
                          }
                        }, 5000);
                      } catch (e) {
                        // Fallback to regular alert if there's any error
                        alert(alertMessage);
                      }
                    } else {
                      alert('Updated and sent to backend!');
                    }
                  }).catch(() => {
                    const submitFailTime = Date.now();
                    const submitDuration = submitFailTime - submitStartTime;
                    
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
                      field_name: itemInfo.name || '',
                      field_type: itemInfo.type || '',
                      suggestion_index: suggestionIdx,
                      submit_duration_ms: submitDuration
                    });
                    
                    // Change button color to red when submission fails
                    if (buttonElement) {
                      buttonElement.style.setProperty('background-color', '#ff4444', 'important');
                      buttonElement.style.setProperty('color', 'white', 'important');
                      // Store state for hover effect
                      buttonElement.setAttribute('data-state', 'failed');
                    }
                    alert('Failed to send to backend.');
                  });
                  break;
              }
            }
          });
        }
      });
    }
  }

})();
