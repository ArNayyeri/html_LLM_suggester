// background.js

// Store suggestion responses to handle popup closing
let suggestionResponses = new Map();

// Handle messages from popup and content scripts
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.type === 'getSuggestionResponse') {
    const response = suggestionResponses.get(request.tabId);
    if (response) {
      sendResponse(response);
      suggestionResponses.delete(request.tabId); // Clean up after sending
    } else {
      sendResponse(null);
    }
    return true;
  }
    if (request.type === 'requestSuggestions') {
    const requestStartTime = request.startTime || Date.now();
    
    // Handle suggestion request from popup
    chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
      if (!tabs[0]) {
        sendResponse({ error: 'No active tab found' });
        return;
      }
      
      const tabId = tabs[0].id;
      
      // Get page snapshot
      chrome.tabs.sendMessage(tabId, { type: 'getPageSnapshot' }, function (response) {
        if (!response || !response.html) {
          sendResponse({ error: 'Could not get page HTML' });
          return;
        }
        
        const serverRequestStartTime = Date.now();
        
        // Send request to Python server
        fetch('http://localhost:5000/suggest_inputs', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ html: response.html })
        })
        .then(res => res.json())
        .then(data => {
          const serverResponseTime = Date.now();
          const serverDuration = serverResponseTime - serverRequestStartTime;
          const totalRequestDuration = serverResponseTime - requestStartTime;
          
          // Store the response with timing info
          suggestionResponses.set(tabId, {
            ...data,
            timing: {
              request_start_time: requestStartTime,
              server_request_start_time: serverRequestStartTime,
              server_response_time: serverResponseTime,
              server_duration_ms: serverDuration,
              total_request_duration_ms: totalRequestDuration
            }
          });
          
          // Try to get the array from data
          let arr = data;
          if (data && data.raw) {
            try { arr = JSON.parse(data.raw); } catch { arr = []; }
          }
          if (!Array.isArray(arr)) {
            arr = [];
          }
          
          // Send suggestions to content script for DOM injection
          chrome.tabs.sendMessage(tabId, { 
            type: 'injectInputSuggestions', 
            suggestions: arr 
          });
          
          sendResponse({ 
            success: true, 
            suggestions: arr,
            timing: {
              server_duration_ms: serverDuration,
              total_request_duration_ms: totalRequestDuration
            }
          });
        })
        .catch(err => {
          const errorTime = Date.now();
          const errorDuration = errorTime - requestStartTime;
          
          const errorResponse = { 
            error: 'Server error: ' + err.message,
            timing: {
              request_start_time: requestStartTime,
              error_time: errorTime,
              error_duration_ms: errorDuration
            }
          };
          suggestionResponses.set(tabId, errorResponse);
          sendResponse(errorResponse);
        });
      });
    });
    return true; // Keep the message channel open for async response
  }
});

// Clean up stored responses when tabs are closed
chrome.tabs.onRemoved.addListener((tabId) => {
  suggestionResponses.delete(tabId);
});