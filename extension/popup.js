const BACKEND_URL = "http://127.0.0.1:5050";

async function checkStatus() {
  const statusIndicator = document.getElementById('api-status');
  const statusText = document.getElementById('status-text');
  const keyWarning = document.getElementById('key-warning');

  try {
    const response = await fetch(`${BACKEND_URL}/health`);
    const data = await response.json();

    if (data.status === 'healthy') {
      statusIndicator.classList.add('online');
      statusText.innerText = 'Connected';
      statusText.style.color = '#4cd137';

      if (!data.key_set) {
        keyWarning.style.display = 'block';
      } else {
        keyWarning.style.display = 'none';
      }
    } else {
      statusIndicator.classList.remove('online');
      statusText.innerText = 'Offline';
      statusText.style.color = '#e84118';
    }
  } catch (err) {
    statusIndicator.classList.remove('online');
    statusText.innerText = 'Offline';
    statusText.style.color = '#e84118';
  }
}

// Handle Auto-Mode Toggle
const autoToggle = document.getElementById('auto-mode-toggle');

chrome.storage.local.get(['autoMode'], (result) => {
  autoToggle.checked = !!result.autoMode;
});

autoToggle.addEventListener('change', () => {
  chrome.storage.local.set({ autoMode: autoToggle.checked });
});

checkStatus();
setInterval(checkStatus, 3000);
