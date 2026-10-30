function checkServerHealth() {
  const statusEl = document.getElementById('server-status');
  const textEl = document.getElementById('server-text');

  fetch('http://localhost:5000/health', { method: 'GET', signal: AbortSignal.timeout(2000) })
    .then(res => res.json())
    .then(data => {
      if (statusEl && textEl) {
        statusEl.className = 'server-status server-online';
        textEl.textContent = data.model || 'Online';
        textEl.title = `Mode: ${data.mode} | Model: ${data.model}`;
      }
    })
    .catch(() => {
      if (statusEl && textEl) {
        statusEl.className = 'server-status server-offline';
        textEl.textContent = 'Offline';
        textEl.title = 'Python server is not running on port 5000';
      }
    });
}

function updateCount() {
  chrome.storage.local.get({ recordedEvents: [] }, function (result) {
    const el = document.getElementById('count');
    if (el) {
      const len = result.recordedEvents ? result.recordedEvents.length : 0;
      el.textContent = `Events recorded: ${len}`;
    }
  });
}

function updateToggleButton() {
  chrome.storage.local.get({ isRecording: false }, function (result) {
    const btn = document.getElementById('toggle-recording');
    if (btn) {
      if (result.isRecording) {
        btn.textContent = '⏹ Stop Recording';
        btn.className = 'btn btn-record-stop';
      } else {
        btn.textContent = '⏺ Start Recording';
        btn.className = 'btn btn-record-start';
      }
    }
  });
}

document.getElementById('toggle-recording').onclick = function () {
  chrome.storage.local.get({ isRecording: false, recordedEvents: [] }, function (result) {
    const wasRecording = result.isRecording;
    const newRecording = !wasRecording;

    if (newRecording) {
      // STARTING RECORDING
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
      // STOPPING RECORDING
      chrome.storage.local.set({ isRecording: false }, function () {
        updateToggleButton();

        const eventsToSend = result.recordedEvents || [];
        fetch('http://localhost:5000/events', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ events: eventsToSend })
        }).then(res => res.json())
          .then(() => {
            chrome.storage.local.set({ serverError: false });
            updateCount();
            alert(`Recording finished!\nSaved ${eventsToSend.length} events and generated Katalon test.`);
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
    const data = JSON.stringify(result.recordedEvents || [], null, 2);
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

const suggestBtn = document.getElementById('suggest-inputs');
suggestBtn.onclick = function () {
  const suggestionStartTime = Date.now();

  suggestBtn.disabled = true;
  suggestBtn.textContent = '⏳ Processing with AI...';

  chrome.runtime.sendMessage({
    type: 'requestSuggestions',
    startTime: suggestionStartTime
  }, function(response) {
    suggestBtn.disabled = false;
    suggestBtn.textContent = '✨ Suggest Inputs (AI)';

    if (response && response.error) {
      alert('Error: ' + response.error);
    } else if (response && response.success) {
      const count = response.suggestions ? response.suggestions.length : 0;
      alert(`Success! Generated suggestions for ${count} field(s).\nLook for the blue '?' buttons next to input fields on the page.`);
    } else {
      alert('Request completed. Check the webpage for suggestions.');
    }
    updateCount();
  });
};

updateCount();
updateToggleButton();
checkServerHealth();
