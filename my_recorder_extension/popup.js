function updateCount() {
  chrome.storage.local.get({ recordedEvents: [] }, function (result) {
    const el = document.getElementById('count');
    if (el) {
      el.textContent = 'Events recorded: ' + (result.recordedEvents ? result.recordedEvents.length : 0);
    }
  });
}

function updateToggleButton() {
  chrome.storage.local.get({ isRecording: false }, function (result) {
    const btn = document.getElementById('toggle-recording');
    if (btn) {
      btn.textContent = result.isRecording ? 'Stop Recording' : 'Start Recording';
      btn.style.backgroundColor = result.isRecording ? '#dc3545' : '#28a745';
      btn.style.color = '#fff';
    }
  });
}

document.getElementById('toggle-recording').onclick = function () {
  chrome.storage.local.get({ isRecording: false, recordedEvents: [] }, function (result) {
    const wasRecording = result.isRecording;
    const newRecording = !wasRecording;

    if (newRecording) {
      // STARTING NEW RECORDING SESSION
      // 1. Get active tab to record initial page URL
      chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
        const activeTab = tabs && tabs[0] ? tabs[0] : null;
        const initialEvents = [];

        if (activeTab && activeTab.url && !activeTab.url.startsWith('chrome')) {
          initialEvents.push({
            type: 'pageload',
            time: Date.now(),
            url: activeTab.url
          });
        }

        // 2. Clear old session events and set recording active
        chrome.storage.local.set({
          isRecording: true,
          recordedEvents: initialEvents,
          serverError: false
        }, function () {
          updateToggleButton();
          updateCount();
        });
      });
    } else {
      // STOPPING RECORDING SESSION
      chrome.storage.local.set({ isRecording: false }, function () {
        updateToggleButton();

        // Send recorded events to Python backend
        const eventsToSend = result.recordedEvents || [];
        fetch('http://localhost:5000/events', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ events: eventsToSend })
        }).then(res => res.json())
          .then(data => {
            chrome.storage.local.set({ serverError: false });
            updateCount();
            alert(`Recording finished! Saved ${eventsToSend.length} events to server and generated Katalon test.`);
          }).catch(error => {
            console.error('Failed to send events:', error);
            chrome.storage.local.set({ serverError: true });
            updateCount();
            alert('Failed to send events to server. Make sure recorder_server.py is running on port 5000.');
          });
      });
    }
  });
};

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

// Suggest input values
const suggestBtn = document.getElementById('suggest-inputs');
suggestBtn.onclick = function () {
  const suggestionStartTime = Date.now();

  suggestBtn.disabled = true;
  suggestBtn.textContent = 'Processing with AI...';

  chrome.runtime.sendMessage({
    type: 'requestSuggestions',
    startTime: suggestionStartTime
  }, function(response) {
    suggestBtn.disabled = false;
    suggestBtn.textContent = 'Suggest Input Values';

    if (response && response.error) {
      alert('Error: ' + response.error);
    } else if (response && response.success) {
      const count = response.suggestions ? response.suggestions.length : 0;
      alert(`Success! Generated suggestions for ${count} field(s). Look for the blue '?' buttons next to input fields on the page.`);
    } else {
      alert('Request completed. Check the webpage for suggestions.');
    }
    updateCount();
  });
};

updateCount();
updateToggleButton();
