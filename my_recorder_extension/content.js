(function () {
  if (window.hasRecorder) return;
  window.hasRecorder = true;

  // Store the currently right-clicked element
  let rightClickedElement = null;

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
    if (!element) return '';
    
    // If element has a unique ID, use it for a shorter XPath
    if (element.id) {
      return `//*[@id="${element.id}"]`;
    }
    
    // For body element
    if (element === document.body) {
      return '/html/body';
    }
    
    // Build XPath by traversing up the DOM tree
    let xpath = '';
    let current = element;
    
    while (current && current.nodeType === 1) { // ELEMENT_NODE
      let tagName = current.tagName.toLowerCase();
      
      if (current === document.documentElement) {
        xpath = '/html' + xpath;
        break;
      }
      
      // Count preceding siblings with the same tag name
      let index = 1;
      let sibling = current.previousElementSibling;
      while (sibling) {
        if (sibling.tagName.toLowerCase() === tagName) {
          index++;
        }
        sibling = sibling.previousElementSibling;
      }
      
      // Count following siblings to see if index is needed
      let hasFollowingSibling = false;
      sibling = current.nextElementSibling;
      while (sibling) {
        if (sibling.tagName.toLowerCase() === tagName) {
          hasFollowingSibling = true;
          break;
        }
        sibling = sibling.nextElementSibling;
      }
      
      // Add index only if there are multiple elements with same tag name
      if (index > 1 || hasFollowingSibling) {
        xpath = `/${tagName}[${index}]` + xpath;
      } else {
        xpath = `/${tagName}` + xpath;
      }
      
      current = current.parentElement;
    }
    
    return xpath;
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
  }); function injectInputSuggestionButtons(suggestions) {
    // Remove any existing suggestion buttons first
    document.querySelectorAll('.input-suggestion-btn').forEach(btn => btn.remove());

    suggestions.forEach((item, idx) => {
      const el = document.getElementById(item.id) || document.querySelector(`[name="${item.name}"]`);
      if (!el) return;

      const btn = document.createElement('button');
      btn.textContent = '?';
      btn.className = 'input-suggestion-btn';
      btn.setAttribute('data-idx', idx);

      // Enhanced CSS for better visibility
      btn.style.cssText = `
      all: initial !important;
      font-family: Arial, sans-serif !important;
      font-size: 14px !important;
      font-weight: bold !important;
      line-height: 1 !important;
      
      /* Size and positioning */
      width: 24px !important;
      height: 24px !important;
      min-width: 24px !important;
      min-height: 24px !important;
      max-width: 24px !important;
      max-height: 24px !important;
      
      /* Visual appearance */
      background: linear-gradient(135deg, #007bff 0%, #0056b3 100%) !important;
      color: white !important;
      border: 2px solid #ffffff !important;
      border-radius: 50% !important;
      
      /* Shadow for visibility */
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3), 
                  0 0 0 1px rgba(0, 123, 255, 0.5) !important;
      
      /* Positioning */
      position: absolute !important;
      z-index: 999999 !important;
      
      /* Layout */
      display: inline-flex !important;
      align-items: center !important;
      justify-content: center !important;
      
      /* Interaction */
      cursor: pointer !important;
      user-select: none !important;
      
      /* Reset all possible inherited styles */
      margin: 0 !important;
      padding: 0 !important;
      text-decoration: none !important;
      text-align: center !important;
      vertical-align: baseline !important;
      white-space: nowrap !important;
      
      /* Transitions */
      transition: all 0.2s ease !important;
      
      /* Ensure visibility */
      opacity: 1 !important;
      visibility: visible !important;
      overflow: visible !important;
      transform: none !important;
      
      /* Text properties */
      text-shadow: none !important;
      text-transform: none !important;
      letter-spacing: normal !important;
      word-spacing: normal !important;
      
      /* Box model */
      box-sizing: border-box !important;
      float: none !important;
      clear: none !important;
    `;

      // Position the button relative to the input field
      const positionButton = () => {
        const rect = el.getBoundingClientRect();
        const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
        const scrollLeft = window.pageXOffset || document.documentElement.scrollLeft;

        // Position to the right of the input field with some margin
        btn.style.setProperty('top', `${rect.top + scrollTop + (rect.height - 24) / 2}px`, 'important');
        btn.style.setProperty('left', `${rect.right + scrollLeft + 8}px`, 'important');
      };

      // Initial positioning
      positionButton();

      // Reposition on scroll and resize
      const repositionHandler = () => {
        if (document.contains(el) && document.contains(btn)) {
          positionButton();
        }
      };

      window.addEventListener('scroll', repositionHandler);
      window.addEventListener('resize', repositionHandler);

      btn.title = 'Click to edit field suggestions';

      // Enhanced hover effects
      btn.addEventListener('mouseenter', function () {
        const state = this.getAttribute('data-state');
        if (!state) {
          this.style.setProperty('transform', 'scale(1.1)', 'important');
          this.style.setProperty('box-shadow', '0 3px 12px rgba(0, 0, 0, 0.4), 0 0 0 2px rgba(0, 123, 255, 0.8)', 'important');
        }
      });

      btn.addEventListener('mouseleave', function () {
        const state = this.getAttribute('data-state');
        if (state === 'confirmed' || state === 'submitted') {
          this.style.setProperty('background', 'linear-gradient(135deg, #28a745 0%, #1e7e34 100%)', 'important');
          this.style.setProperty('transform', 'scale(1)', 'important');
          this.style.setProperty('box-shadow', '0 2px 8px rgba(0, 0, 0, 0.3), 0 0 0 1px rgba(40, 167, 69, 0.5)', 'important');
        } else if (state === 'cancelled' || state === 'failed') {
          this.style.setProperty('background', 'linear-gradient(135deg, #dc3545 0%, #bd2130 100%)', 'important');
          this.style.setProperty('transform', 'scale(1)', 'important');
          this.style.setProperty('box-shadow', '0 2px 8px rgba(0, 0, 0, 0.3), 0 0 0 1px rgba(220, 53, 69, 0.5)', 'important');
        } else {
          this.style.setProperty('transform', 'scale(1)', 'important');
          this.style.setProperty('box-shadow', '0 2px 8px rgba(0, 0, 0, 0.3), 0 0 0 1px rgba(0, 123, 255, 0.5)', 'important');
        }
      });

      // State-based styling
      const updateButtonState = (state) => {
        btn.setAttribute('data-state', state);
        switch (state) {
          case 'confirmed':
          case 'submitted':
            btn.style.setProperty('background', 'linear-gradient(135deg, #28a745 0%, #1e7e34 100%)', 'important');
            btn.style.setProperty('border-color', '#ffffff', 'important');
            btn.style.setProperty('box-shadow', '0 2px 8px rgba(0, 0, 0, 0.3), 0 0 0 1px rgba(40, 167, 69, 0.5)', 'important');
            break;
          case 'cancelled':
          case 'failed':
            btn.style.setProperty('background', 'linear-gradient(135deg, #dc3545 0%, #bd2130 100%)', 'important');
            btn.style.setProperty('border-color', '#ffffff', 'important');
            btn.style.setProperty('box-shadow', '0 2px 8px rgba(0, 0, 0, 0.3), 0 0 0 1px rgba(220, 53, 69, 0.5)', 'important');
            break;
          default:
            btn.style.setProperty('background', 'linear-gradient(135deg, #007bff 0%, #0056b3 100%)', 'important');
            btn.style.setProperty('border-color', '#ffffff', 'important');
            btn.style.setProperty('box-shadow', '0 2px 8px rgba(0, 0, 0, 0.3), 0 0 0 1px rgba(0, 123, 255, 0.5)', 'important');
        }
      };

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

        try {
          showEditModal(item, idx, suggestions, questionMarkClickTime);
        } catch (err) {
          console.error('Failed to open popup:', err);
          alert('Failed to open popup window. Please check if popup blocking is enabled.');
        }
      };

      // Append to body instead of next to the element to avoid layout issues
      document.body.appendChild(btn);

      // Store reference for state updates
      btn.updateState = updateButtonState;
    });
  }  // Move the message listener setup outside the showEditModal function to ensure it's always available
  if (!window.hasSetupMessageListener) {
    window.hasSetupMessageListener = true;
    
    window.addEventListener('message', function(event) {
      // Process messages from popup windows
      if (event.data && event.data.action) {
        const eventData = event.data;
        const itemInfo = eventData.itemInfo;
        
        if (!itemInfo) return;
        
        // Find the relevant suggestion
        let suggestionIdx = itemInfo.idx;
        
        // Get the button element to change its color
        const buttonElement = document.querySelector(`.input-suggestion-btn[data-idx="${suggestionIdx}"]`);
        
        if (!buttonElement) {
          console.error('Button element not found for index:', suggestionIdx);
          return;
        }
        
        // Handle different actions
        switch (eventData.action) {
          case 'cancelEdit':
            console.log('Processing cancel edit for button:', suggestionIdx);
            
            // Force button color to red when cancelled
            buttonElement.setAttribute('data-state', 'cancelled');
            buttonElement.style.setProperty('background', 'linear-gradient(135deg, #dc3545 0%, #bd2130 100%)', 'important');
            buttonElement.style.setProperty('border-color', '#ffffff', 'important');
            buttonElement.style.setProperty('box-shadow', '0 2px 8px rgba(0, 0, 0, 0.3), 0 0 0 1px rgba(220, 53, 69, 0.5)', 'important');
            
            console.log('Button color changed to red for cancel');
            break;
            
          case 'confirmEdit':
            console.log('Processing confirm edit for button:', suggestionIdx);
            
            // Force button color to green when confirmed
            buttonElement.setAttribute('data-state', 'confirmed');
            buttonElement.style.setProperty('background', 'linear-gradient(135deg, #28a745 0%, #1e7e34 100%)', 'important');
            buttonElement.style.setProperty('border-color', '#ffffff', 'important');
            buttonElement.style.setProperty('box-shadow', '0 2px 8px rgba(0, 0, 0, 0.3), 0 0 0 1px rgba(40, 167, 69, 0.5)', 'important');
            
            console.log('Button color changed to green for confirm');
            break;
            
          case 'submitEdit':
            console.log('Processing submit edit for button:', suggestionIdx);
            
            // Get the values from the message
            const newRange = eventData.data.range;
            const newExamples = eventData.data.examples;
            const newBadExamples = eventData.data.bad_examples || [];
            
            console.log('Submit data received:', { newRange, newExamples, newBadExamples });
            
            // FIRST: Update the local storage immediately with new values
            chrome.storage.local.get({ currentSuggestions: [] }, function(result) {
              const currentSuggestions = result.currentSuggestions || [];
              
              if (suggestionIdx < currentSuggestions.length) {
                // Update the suggestion in memory with new values
                currentSuggestions[suggestionIdx].range = newRange;
                currentSuggestions[suggestionIdx].examples = newExamples;
                currentSuggestions[suggestionIdx].bad_examples = newBadExamples;
                
                console.log('Updating local storage with:', { range: newRange, examples: newExamples, bad_examples: newBadExamples });
                
                // Save updated suggestions to storage immediately
                chrome.storage.local.set({ currentSuggestions: currentSuggestions }, function() {
                  console.log('Updated suggestion stored locally:', currentSuggestions[suggestionIdx]);
                  
                  // Send completion message to popup IMMEDIATELY
                  if (event.source && !event.source.closed) {
                    console.log('Sending submitComplete message to popup');
                    event.source.postMessage({
                      action: 'submitComplete',
                      success: true,
                      suggestion: currentSuggestions[suggestionIdx]
                    }, '*');
                  }
                  
                  // Change button color to green immediately
                  buttonElement.setAttribute('data-state', 'submitted');
                  buttonElement.style.setProperty('background', 'linear-gradient(135deg, #28a745 0%, #1e7e34 100%)', 'important');
                  buttonElement.style.setProperty('border-color', '#ffffff', 'important');
                  buttonElement.style.setProperty('box-shadow', '0 2px 8px rgba(0, 0, 0, 0.3), 0 0 0 1px rgba(40, 167, 69, 0.5)', 'important');
                  
                  console.log('Button color changed to green for submit');
                  
                  // THEN: Send to backend and UPDATE LOCAL STORAGE WITH SERVER RESPONSE
                  fetch('http://localhost:5000/update_input_suggestion', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                      field: itemInfo.name || itemInfo.id,
                      range: newRange,
                      examples: newExamples,
                      bad_examples: newBadExamples
                    })
                  })
                  .then(res => res.json())
                  .then(data => {
                    console.log('Backend update successful:', data);
                    
                    // UPDATE LOCAL STORAGE WITH SERVER RESPONSE
                    chrome.storage.local.get({ currentSuggestions: [] }, function(storageResult) {
                      const updatedSuggestions = storageResult.currentSuggestions || [];
                      
                      if (suggestionIdx < updatedSuggestions.length) {
                        // Update with server response values
                        if (data.range !== undefined) {
                          updatedSuggestions[suggestionIdx].range = data.range;
                          console.log('Updated range from server:', data.range);
                        }
                        if (data.new_examples !== undefined) {
                          updatedSuggestions[suggestionIdx].examples = data.new_examples;
                          console.log('Updated examples from server:', data.new_examples);
                        }
                        if (data.new_bad_examples !== undefined) {
                          updatedSuggestions[suggestionIdx].bad_examples = data.new_bad_examples;
                          console.log('Updated bad examples from server:', data.new_bad_examples);
                        }
                        
                        // Save the server-updated data to storage
                        chrome.storage.local.set({ currentSuggestions: updatedSuggestions }, function() {
                          console.log('Server response stored in local storage:', updatedSuggestions[suggestionIdx]);
                          
                          // Send another completion message with updated data
                          if (event.source && !event.source.closed) {
                            console.log('Sending server update to popup');
                            event.source.postMessage({
                              action: 'serverUpdateComplete',
                              success: true,
                              suggestion: updatedSuggestions[suggestionIdx]
                            }, '*');
                          }
                        });
                      }
                    });
                    
                    // Show success notification
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
                    `;
                    notification.innerHTML = '<strong>Suggestion updated successfully!</strong><br>Good and bad examples saved.';
                    document.body.appendChild(notification);
                    
                    setTimeout(() => {
                      if (notification.parentNode) {
                        notification.parentNode.removeChild(notification);
                      }
                    }, 3000);
                  })
                  .catch(error => {
                    console.error('Backend update failed:', error);
                    // Don't change button color back - keep the local changes
                  });
                });
              } else {
                console.error('Invalid suggestion index:', suggestionIdx);
              }
            });
            break;
        }
      }
    });
  }

  function showEditModal(item, idx, suggestions, questionMarkClickTime) {
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
    chrome.storage.local.get({ currentSuggestions: [] }, function (result) {
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

      if (currentItem.bad_examples && currentItem.bad_examples.length > 0) {
        params.append('bad_examples', JSON.stringify(currentItem.bad_examples));
      }

      const popupURL = `${extensionURL}?${params.toString()}`;

      // Open popup window
      const popupWidth = 650;  // Increased width for bad examples
      const popupHeight = 550; // Increased height for bad examples
      const left = (window.screen.width / 2) - (popupWidth / 2);
      const top = (window.screen.height / 2) - (popupHeight / 2);

      const uniqueWindowName = `edit_field_${idx}_${Date.now()}`;

      const popupWindow = window.open(
        popupURL,
        uniqueWindowName,
        `width=${popupWidth},height=${popupHeight},left=${left},top=${top},resizable=yes,scrollbars=yes,status=no,location=no,menubar=no,toolbar=no`
      );

      if (popupWindow) {
        popupWindow.focus();
      } else {
        alert('Popup window was blocked. Please allow popups for this website.');
      }
    });
  }

  // Track right-clicked element
  document.addEventListener('contextmenu', function(e) {
    rightClickedElement = e.target;
  }, true);

  // Function to get element text content
  function getElementText(element) {
    if (!element) return '';
    
    // For input elements, get the value
    if (element.tagName === 'INPUT' || element.tagName === 'TEXTAREA') {
      return element.value || '';
    }
    
    // For other elements, get text content
    return element.textContent.trim() || element.innerText.trim() || '';
  }

  // Function to get target selector for an element
  function getTargetSelector(element) {
    if (!element) return '';
    
    // For verification commands, ALWAYS use XPath
    return `xpath=${getXPath(element)}`;
  }

  // Function to determine appropriate value based on command and element
  function getValueForCommand(command, element) {
    const text = getElementText(element);
    
    switch (command) {
      case 'verifyTitle':
      case 'assertTitle':
      case 'storeTitle':
        return document.title;
        
      case 'verifyText':
      case 'assertText':
      case 'storeText':
      case 'waitForTextPresent':
      case 'waitForTextNotPresent':
        return text;
        
      case 'verifyValue':
      case 'assertValue':
      case 'storeValue':
      case 'waitForValue':
      case 'waitForNotValue':
        // For input elements, return the value
        if (element.tagName === 'INPUT' || element.tagName === 'TEXTAREA') {
          return element.value || '';
        }
        // For other elements, return text content
        return text;
        
      case 'waitForElementPresent':
      case 'waitForElementNotPresent':
      case 'waitForVisible':
      case 'waitForNotVisible':
        return ''; // These commands don't need a value
        
      default:
        return text;
    }
  }

  // Function to record verification command
  function recordVerificationCommand(command, element) {
    if (!element) {
      console.warn('No element selected for verification command');
      return;
    }

    // Always use XPath for verification commands
    const target = `xpath=${getXPath(element)}`;
    const value = getValueForCommand(command, element);
    const currentTime = Date.now();

    // Create the recorded event
    const details = {
      type: 'verification_command',
      command: command,
      target: target,  // This will always be an XPath
      value: value,
      time: currentTime,
      url: window.location.href,
      element_tag: element.tagName,
      element_id: element.id || '',
      element_class: element.className || '',
      xpath: getXPath(element)
    };

    console.log('Recording verification command:', details);

    // Record the event
    record(details);
    
    // Send snapshot
    sendSnapshotToPython('verification_command', details);

    // Show visual feedback
    showCommandRecordedFeedback(command, target, value);
  }

  // Function to show visual feedback when command is recorded
  function showCommandRecordedFeedback(command, target, value) {
    const feedback = document.createElement('div');
    feedback.style.cssText = `
      position: fixed;
      top: 20px;
      right: 20px;
      background: #4CAF50;
      color: white;
      padding: 12px 16px;
      border-radius: 6px;
      z-index: 999999;
      font-family: Arial, sans-serif;
      font-size: 14px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.3);
      max-width: 400px;
      word-wrap: break-word;
    `;
    
    // Truncate XPath if too long for display
    const displayTarget = target.length > 50 ? target.substring(0, 47) + '...' : target;
    
    feedback.innerHTML = `
      <strong>Command Recorded:</strong><br>
      <code style="background: rgba(255,255,255,0.2); padding: 2px 4px; border-radius: 3px;">${command}</code><br>
      <small><strong>XPath:</strong> ${displayTarget}</small><br>
      ${value ? `<small><strong>Value:</strong> ${value}</small>` : ''}
    `;
    
    document.body.appendChild(feedback);
    
    // Remove feedback after 4 seconds (longer since XPath might be complex)
    setTimeout(() => {
      if (feedback.parentNode) {
        feedback.parentNode.removeChild(feedback);
      }
    }, 4000);
  }

  // Listen for messages from background script
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    // ...existing message handling...

    if (request && request.type === 'recordVerificationCommand') {
      const command = request.command;
      
      if (rightClickedElement) {
        recordVerificationCommand(command, rightClickedElement);
        sendResponse({ success: true, command: command });
      } else {
        console.warn('No right-clicked element found');
        sendResponse({ success: false, error: 'No element selected' });
      }
      return true;
    }

    // ...rest of existing message handling...
    return true;
  });

  // ...rest of existing code...
})();