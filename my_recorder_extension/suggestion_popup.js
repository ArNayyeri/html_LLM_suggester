// This file manages the functionality for the suggestion popup window
// Used in conjunction with suggestion_popup.html

// Track if user has made changes to prevent overwriting
let userHasEditedRange = false;
let userHasEditedExamples = false;

// Get query parameters from URL
function getQueryParams() {
  const params = {};
  const queryString = window.location.search.substring(1);
  const pairs = queryString.split('&');
  
  for (const pair of pairs) {
    const [key, value] = pair.split('=');
    if (key && value) {
      params[decodeURIComponent(key)] = decodeURIComponent(value);
    }
  }
  
  return params;
}

// Handle messages to parent window
function sendMessageToParent(action, data = {}) {
  if (!window.opener) return;
  
  const queryParams = getQueryParams();
  const itemInfo = {
    id: queryParams.id || '',
    name: queryParams.name || '',
    type: queryParams.type || '',
    idx: parseInt(queryParams.idx || '0')
  };
  
  window.opener.postMessage({
    action: action,
    itemInfo: itemInfo,
    time: Date.now(),
    data: data
  }, '*');
}

// Function to fetch the latest data from storage
function fetchLatestData() {
  const params = getQueryParams();
  const idx = parseInt(params.idx || '0');
  
  // Only proceed if we have a valid index
  if (isNaN(idx)) return;
  
  // Connect to chrome extension API
  if (chrome && chrome.runtime && chrome.runtime.id) {
    // We're in a Chrome extension context
    chrome.runtime.sendMessage({
      type: 'getSuggestion',
      idx: idx,
      id: params.id || '',
      name: params.name || ''
    }, function(response) {
      if (response && response.suggestion) {
        updateUIWithSuggestion(response.suggestion);
      }
    });
  } else {
    // Fallback to URL parameters if we can't access Chrome API
    updateUIFromParams();
  }
}

// Update the UI with suggestion data from storage
function updateUIWithSuggestion(suggestion) {
  // Display field name
  document.getElementById('field-name').textContent = suggestion.name || suggestion.id || '(Unnamed Field)';
  
  // Only update values if user hasn't edited them
  if (!userHasEditedRange && suggestion.range) {
    document.getElementById('edit-range').value = suggestion.range;
  }
  
  if (!userHasEditedExamples && suggestion.examples && Array.isArray(suggestion.examples)) {
    document.getElementById('edit-examples').value = suggestion.examples.join('\n');
  }
}

// Update the UI from URL parameters (fallback)
function updateUIFromParams() {
  const params = getQueryParams();
  
  // Display field name
  document.getElementById('field-name').textContent = params.name || params.id || '(Unnamed Field)';
  
  // Only set initial values if user hasn't edited them
  if (!userHasEditedRange && params.range) {
    try {
      document.getElementById('edit-range').value = decodeURIComponent(params.range);
    } catch (e) {
      console.error('Failed to decode range:', e);
      document.getElementById('edit-range').value = params.range;
    }
  }
  
  if (!userHasEditedExamples && params.examples) {
    try {
      const examples = JSON.parse(decodeURIComponent(params.examples));
      document.getElementById('edit-examples').value = examples.join('\n');
    } catch (e) {
      console.error('Failed to parse examples:', e);
      try {
        document.getElementById('edit-examples').value = decodeURIComponent(params.examples);
      } catch {
        document.getElementById('edit-examples').value = params.examples;
      }
    }
  }
}

// Listen for messages from the parent window (for real-time updates)
window.addEventListener('message', function(event) {
  if (event.data && event.data.action === 'updateSuggestionData') {
    if (event.data.suggestion) {
      // Update the UI with the new data
      updateUIWithSuggestion(event.data.suggestion);
      
      // Add a visual indicator that the data was updated
      const fieldInfo = document.getElementById('field-info');
      if (fieldInfo) {
        const updateIndicator = document.createElement('span');
        updateIndicator.textContent = ' ✓ Updated';
        updateIndicator.style.color = '#28a745';
        updateIndicator.style.fontWeight = 'bold';
        
        // Remove any existing indicators
        const existingIndicator = fieldInfo.querySelector('.update-indicator');
        if (existingIndicator) {
          fieldInfo.removeChild(existingIndicator);
        }
        
        updateIndicator.className = 'update-indicator';
        fieldInfo.appendChild(updateIndicator);
        
        // Remove the indicator after a few seconds
        setTimeout(() => {
          if (updateIndicator.parentNode) {
            updateIndicator.parentNode.removeChild(updateIndicator);
          }
        }, 3000);
      }
    }
  }
});

// Initialize the popup with data
document.addEventListener('DOMContentLoaded', function() {
  const params = getQueryParams();
  
  // Check if we have the basic required parameters
  if (!params.idx) {
    document.body.innerHTML = '<div style="color:red;padding:20px;text-align:center;">Error: Missing required parameters</div>';
    setTimeout(() => window.close(), 3000);
    return;
  }
  
  // First load data from URL parameters (for immediate display)
  updateUIFromParams();
  
  // Then try to fetch the latest data from storage
  fetchLatestData();
  
  // Set up change tracking for text areas
  const rangeTextarea = document.getElementById('edit-range');
  const examplesTextarea = document.getElementById('edit-examples');
  
  rangeTextarea.addEventListener('input', function() {
    userHasEditedRange = true;
  });
  
  examplesTextarea.addEventListener('input', function() {
    userHasEditedExamples = true;
  });
  
  // Set up a refresh interval to periodically check for updates
  // But only update if user hasn't edited the fields
  setInterval(fetchLatestData, 5000); // Check every 5 seconds
  
  // Set up button event handlers
  document.getElementById('edit-cancel').addEventListener('click', function() {
    sendMessageToParent('cancelEdit');
    window.close();
  });
  
  document.getElementById('edit-confirm').addEventListener('click', function() {
    sendMessageToParent('confirmEdit');
    window.close();
  });
  
  document.getElementById('edit-submit').addEventListener('click', function() {
    // Get values
    const range = document.getElementById('edit-range').value;
    const examples = document.getElementById('edit-examples').value
      .split('\n')
      .map(s => s.trim())
      .filter(Boolean);
    
    sendMessageToParent('submitEdit', {
      range: range,
      examples: examples
    });
    
    // Don't close immediately to prevent race conditions
    setTimeout(() => window.close(), 100);
  });
});
