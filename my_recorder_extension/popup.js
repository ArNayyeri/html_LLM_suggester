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

// Patch the suggest-inputs button handler to inject suggestions into the page
const suggestBtn = document.getElementById('suggest-inputs');
suggestBtn.onclick = function () {
  // Get the active tab
  chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
    if (!tabs[0]) return;
    chrome.tabs.sendMessage(tabs[0].id, { type: 'getPageSnapshot' }, function (response) {
      if (!response || !response.html) {
        alert('Could not get page HTML.');
        return;
      }
      fetch('http://localhost:5000/suggest_inputs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ html: response.html })
      })
        .then(res => res.json())
        .then(data => {
          // Try to get the array from data
          let arr = data;
          if (data && data.raw) {
            try { arr = JSON.parse(data.raw); } catch { arr = []; }
          }
          if (!Array.isArray(arr)) {
            alert('No input suggestions found.');
            return;
          }
          // Send suggestions to content script for DOM injection
          chrome.tabs.sendMessage(tabs[0].id, { type: 'injectInputSuggestions', suggestions: arr });
        })
        .catch(err => {
          alert('Error: ' + err);
        });
    });
  });
};

updateCount();
updateToggleButton();