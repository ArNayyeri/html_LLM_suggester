// background.js

// Store suggestion responses to handle popup closing
let suggestionResponses = new Map();

// Handle messages from popup and content scripts
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.type === 'getSuggestion') {
    // Get the latest suggestion data from storage for a specific index
    chrome.storage.local.get({ currentSuggestions: [] }, function(result) {
      const currentSuggestions = result.currentSuggestions || [];
      const idx = request.idx;
      
      if (idx >= 0 && idx < currentSuggestions.length) {
        const suggestion = currentSuggestions[idx];
        
        // Verify this is the same field (prevent confusion if the indexes change)
        if ((request.id && suggestion.id === request.id) ||
            (request.name && suggestion.name === request.name) ||
            (!request.id && !request.name)) { // Fallback if no identifiers
          sendResponse({ suggestion: suggestion });
        } else {
          sendResponse({ error: 'Field mismatch' });
        }
      } else {
        sendResponse({ error: 'Invalid suggestion index' });
      }
    });
    return true; // Keep the message channel open for async response
  }
  
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
        .then(res => {
          if (!res.ok) {
            throw new Error(`HTTP ${res.status}: ${res.statusText}`);
          }
          return res.json();
        })
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
            try { 
              arr = JSON.parse(data.raw); 
            } catch (e) { 
              console.error('Failed to parse suggestions:', e);
              arr = []; 
            }
          }
          
          if (!Array.isArray(arr)) {
            arr = [];
          }
          
          // Store suggestions in local storage for popup access
          chrome.storage.local.set({ currentSuggestions: arr });
          
          // Send suggestions to content script for DOM injection
          chrome.tabs.sendMessage(tabId, { 
            type: 'injectInputSuggestions', 
            suggestions: arr 
          }, function(injectionResponse) {
            // Handle injection response (optional)
            if (chrome.runtime.lastError) {
              console.warn('Injection message failed:', chrome.runtime.lastError.message);
            }
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
          console.error('Server request failed:', err);
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
  
  // If none of the above conditions match, don't return true
  // This prevents the "asynchronous response" error for unhandled message types
  return false;
});

// Clean up stored responses when tabs are closed
chrome.tabs.onRemoved.addListener((tabId) => {
  suggestionResponses.delete(tabId);
});

// Set up periodic sync for any failed confirmations
function setupPeriodicSync() {
  // Try to sync failed confirmations every 5 minutes
  setInterval(syncPendingConfirmations, 5 * 60 * 1000);
  
  // Also sync on extension startup
  syncPendingConfirmations();
}

// Function to sync any pending confirmations
function syncPendingConfirmations() {
  console.log("Checking for pending confirmations to sync...");
  
  chrome.storage.local.get({ failedConfirmations: [] }, function(result) {
    const failedConfirmations = result.failedConfirmations || [];
    
    if (failedConfirmations.length === 0) {
      console.log("No pending confirmations to sync");
      return;
    }
    
    console.log(`Found ${failedConfirmations.length} pending confirmations to sync`);
    
    // Process each confirmation sequentially to avoid overwhelming the server
    syncNextConfirmation(failedConfirmations, 0, []);
  });
}

// Process confirmations one by one
function syncNextConfirmation(confirmations, index, results) {
  if (index >= confirmations.length) {
    // All done, update storage with remaining failed ones
    const stillFailed = confirmations.filter((_, i) => results[i] === false);
    chrome.storage.local.set({ failedConfirmations: stillFailed });
    
    const successCount = results.filter(r => r === true).length;
    console.log(`Successfully synced ${successCount} of ${confirmations.length} confirmations`);
    return;
  }
  
  const item = confirmations[index];
  
  fetch('http://localhost:5000/confirm_suggestion', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(item)
  })
  .then(response => {
    if (!response.ok) {
      throw new Error(`HTTP error! Status: ${response.status}`);
    }
    return response.json();
  })
  .then(() => {
    results[index] = true; // Success
    console.log(`Successfully synced confirmation ${index + 1} of ${confirmations.length}`);
  })
  .catch(err => {
    results[index] = false; // Failed
    console.error(`Failed to sync confirmation ${index + 1}: ${err.message}`);
  })
  .finally(() => {
    // Process next one with slight delay to not overload server
    setTimeout(() => syncNextConfirmation(confirmations, index + 1, results), 500);
  });
}

// Start periodic sync
setupPeriodicSync();