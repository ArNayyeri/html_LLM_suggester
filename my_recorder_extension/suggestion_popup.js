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

// Update the UI with suggestion data from storage
function updateUIWithSuggestion(suggestion) {
  console.log('Updating UI with suggestion:', suggestion);
  
  // Display field name
  document.getElementById('field-name').textContent = suggestion.name || suggestion.id || '(Unnamed Field)';
  
  // Only update if user hasn't edited these fields
  if (!userHasEditedRange) {
    const rangeTextarea = document.getElementById('edit-range');
    rangeTextarea.value = suggestion.range || '';
    console.log('Updated range field with:', suggestion.range);
  }
  
  if (!userHasEditedExamples) {
    const examplesTextarea = document.getElementById('edit-examples');
    if (suggestion.examples && Array.isArray(suggestion.examples)) {
      examplesTextarea.value = suggestion.examples.join('\n');
      console.log('Updated examples field with:', suggestion.examples);
    } else {
      examplesTextarea.value = '';
    }
  }
}

// Function to fetch the latest data from storage
function fetchLatestData() {
  const params = getQueryParams();
  const idx = parseInt(params.idx || '0');
  
  // Only proceed if we have a valid index
  if (isNaN(idx)) return;
  
  console.log('Fetching latest data for index:', idx);
  
  // Connect to chrome extension API
  if (chrome && chrome.runtime && chrome.runtime.id) {
    // We're in a Chrome extension context
    chrome.runtime.sendMessage({
      type: 'getSuggestion',
      idx: idx,
      id: params.id || '',
      name: params.name || ''
    }, function(response) {
      console.log('Response from getSuggestion:', response);
      
      if (chrome.runtime.lastError) {
        console.error('Chrome runtime error:', chrome.runtime.lastError);
        updateUIFromParams(); // Fallback to URL params
        return;
      }
      
      if (response && response.suggestion) {
        console.log('Updating UI with fresh suggestion data:', response.suggestion);
        updateUIWithSuggestion(response.suggestion);
        
        // Add a visual indicator that data was refreshed
        const indicator = document.createElement('div');
        indicator.style.cssText = `
          position: fixed;
          bottom: 10px;
          right: 10px;
          background: #007bff;
          color: white;
          padding: 5px 10px;
          border-radius: 3px;
          font-size: 12px;
          z-index: 999999;
        `;
        indicator.textContent = 'Data refreshed';
        document.body.appendChild(indicator);
        
        setTimeout(() => {
          if (indicator.parentNode) {
            indicator.parentNode.removeChild(indicator);
          }
        }, 2000);
      } else if (response && response.error) {
        console.error('Error getting suggestion:', response.error);
        updateUIFromParams(); // Fallback to URL params
      } else {
        console.log('No suggestion data received, using URL params');
        updateUIFromParams(); // Fallback to URL params
      }
    });
  } else {
    // Fallback to URL parameters if we can't access Chrome API
    console.log('Chrome API not available, using URL params');
    updateUIFromParams();
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
  
  // Modified submit button handler
  document.getElementById('edit-submit').addEventListener('click', function() {
    // Get values
    const range = document.getElementById('edit-range').value;
    const examples = document.getElementById('edit-examples').value
      .split('\n')
      .map(s => s.trim())
      .filter(Boolean);

    console.log('Submitting changes:', { range, examples });

    // Show a loading indicator immediately
    const submitBtn = document.getElementById('edit-submit');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Submitting...';
    
    // Send the submit message
    sendMessageToParent('submitEdit', {
      range: range,
      examples: examples
    });

    // Set up a timeout in case we don't get a response
    const timeout = setTimeout(() => {
      console.log('Submit timeout, closing window');
      submitBtn.disabled = false;
      submitBtn.textContent = 'Submit';
      window.close();
    }, 5000);

    // Listen for completion message from parent
    function submitCompleteHandler(event) {
      if (event.data && (event.data.action === 'submitComplete' || event.data.action === 'serverUpdateComplete')) {
        console.log('Submit complete received:', event.data);
        
        if (event.data.action === 'submitComplete') {
          clearTimeout(timeout);
          
          // Re-enable button
          submitBtn.disabled = false;
          submitBtn.textContent = 'Submit';
        }
        
        // Update the UI with the new data immediately
        if (event.data.suggestion) {
          console.log('Updating UI with submitted data:', event.data.suggestion);
          
          // Force update the UI even if user has edited (since this is the final server response)
          if (event.data.action === 'serverUpdateComplete') {
            userHasEditedRange = false;
            userHasEditedExamples = false;
          }
          
          updateUIWithSuggestion(event.data.suggestion);
          
          // Show success message only for initial submit complete
          if (event.data.action === 'submitComplete') {
            const successMsg = document.createElement('div');
            successMsg.style.cssText = `
              position: fixed;
              top: 10px;
              left: 10px;
              right: 10px;
              background: #28a745;
              color: white;
              padding: 10px;
              border-radius: 4px;
              text-align: center;
              font-weight: bold;
              z-index: 999999;
            `;
            successMsg.textContent = 'Changes saved successfully!';
            document.body.appendChild(successMsg);
            
            setTimeout(() => {
              if (successMsg.parentNode) {
                successMsg.parentNode.removeChild(successMsg);
              }
            }, 2000);
            
            // Close window after showing success
            setTimeout(() => window.close(), 2500);
          } else if (event.data.action === 'serverUpdateComplete') {
            // Show a subtle indicator for server update
            const updateMsg = document.createElement('div');
            updateMsg.style.cssText = `
              position: fixed;
              bottom: 10px;
              right: 10px;
              background: #007bff;
              color: white;
              padding: 5px 10px;
              border-radius: 3px;
              font-size: 12px;
              z-index: 999999;
            `;
            updateMsg.textContent = 'Server updated';
            document.body.appendChild(updateMsg);
            
            setTimeout(() => {
              if (updateMsg.parentNode) {
                updateMsg.parentNode.removeChild(updateMsg);
              }
            }, 1500);
          }
        }
        
        // Remove this listener for submitComplete only
        if (event.data.action === 'submitComplete') {
          window.removeEventListener('message', submitCompleteHandler);
        }
      }
    }
    
    window.addEventListener('message', submitCompleteHandler);
  });
});
