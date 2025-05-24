function updateCount() {
  chrome.storage.local.get({ recordedEvents: [] }, function (result) {
    document.getElementById('count').textContent =
      'Events recorded: ' + result.recordedEvents.length;
  });
}

function updateToggleButton() {
  chrome.storage.local.get({ isRecording: false }, function (result) {
    document.getElementById('toggle-recording').textContent =
      result.isRecording ? 'Stop Recording' : 'Start Recording';
  });
}

document.getElementById('toggle-recording').onclick = function () {
  chrome.storage.local.get({ isRecording: false, recordedEvents: [] }, function (result) {
    const wasRecording = result.isRecording;
    const newRecording = !wasRecording;
    chrome.storage.local.set({ isRecording: newRecording }, function () {
      updateToggleButton();
      // If stopping recording, send events to Python backend
      if (wasRecording && !newRecording) {
        fetch('http://localhost:5000/events', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ events: result.recordedEvents })
        }).then(() => {
          chrome.storage.local.set({ serverError: false });
          updateCount();
        }).catch(error => {
          console.error('Failed to send events:', error);
          chrome.storage.local.set({ serverError: true });
          updateCount();
        });
      }
    });
  });
}

document.getElementById('download').onclick = function () {
  chrome.storage.local.get({ recordedEvents: [] }, function (result) {
    const data = JSON.stringify(result.recordedEvents, null, 2);
    const url = URL.createObjectURL(new Blob([data], { type: 'application/json' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = 'recorded_events.json';
    a.click();
    URL.revokeObjectURL(url);
  });
};

document.getElementById('clear').onclick = function () {
  chrome.storage.local.set({ recordedEvents: [] }, updateCount);
};

// Patch the suggest-inputs button handler to use background script
const suggestBtn = document.getElementById('suggest-inputs');
suggestBtn.onclick = function () {
  // Record the start time for suggestion request
  const suggestionStartTime = Date.now();
  
  // Record the suggestion request start event
  chrome.storage.local.get({ recordedEvents: [] }, function (result) {
    const events = result.recordedEvents;
    events.push({
      type: 'suggest_inputs_start',
      time: suggestionStartTime,
      url: window.location ? window.location.href : 'popup',
      tag: 'BUTTON',
      id: 'suggest-inputs',
      class: 'extension-action',
      value: null,
      x: null,
      y: null,
      xpath: null
    });
    chrome.storage.local.set({ recordedEvents: events });
  });
  
  // Disable button during request
  suggestBtn.disabled = true;
  suggestBtn.textContent = 'Processing...';
  
  // Send message to background script
  chrome.runtime.sendMessage({
    type: 'requestSuggestions',
    startTime: suggestionStartTime
  }, function(response) {
    const suggestionEndTime = Date.now();
    const processingDuration = suggestionEndTime - suggestionStartTime;
    
    // Re-enable button
    suggestBtn.disabled = false;
    suggestBtn.textContent = 'Suggest Input Values';
    
    // Record the suggestion request completion event
    chrome.storage.local.get({ recordedEvents: [] }, function (result) {
      const events = result.recordedEvents;
      events.push({
        type: 'suggest_inputs_complete',
        time: suggestionEndTime,
        url: window.location ? window.location.href : 'popup',
        tag: 'BUTTON',
        id: 'suggest-inputs',
        class: 'extension-action',
        value: null,
        x: null,
        y: null,
        xpath: null,
        duration_ms: processingDuration,
        success: response && response.success,
        error: response && response.error ? response.error : null
      });
      chrome.storage.local.set({ recordedEvents: events });
    });
    
    if (response && response.error) {
      alert('Error: ' + response.error);
    } else if (response && response.success) {
      alert('Suggestions injected successfully! Look for ? buttons next to input fields.');
    } else {
      // Check if we can get the response from background (in case popup was closed)
      chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
        if (tabs[0]) {
          chrome.runtime.sendMessage({
            type: 'getSuggestionResponse',
            tabId: tabs[0].id
          }, function(storedResponse) {
            if (storedResponse) {
              alert('Suggestions were processed while popup was closed. Check the page for ? buttons.');
            } else {
              alert('No suggestions found or request failed.');
            }
          });
        }
      });
    }
  });
};

updateCount();
updateToggleButton();