console.log("LeetCode-NVIDIA-AUTO: Content script loaded");

const BACKEND_URL = "http://127.0.0.1:5050";
let autoMode = false;
let fixAttempts = 0;
const MAX_FIX_ATTEMPTS = 25; // Increased for better persistence
let isTesting = false; let isSubmitting = false; let isHandlingError = false;
let isWaitingLC = false; // Flag for LeetCode rate limit cooldown
let isWaitingFinal = false; // Flag to ensure final submission completes

let timerInterval = null;
let startTime = null;
let countdownDuration = 0;
let modelList = []; // Dynamically loaded from backend

// ===================== UI COMPONENTS =====================

function createHUD() {
  if (document.getElementById('lc-nvidia-hud')) return;
  const hud = document.createElement('div');
  hud.id = 'lc-nvidia-hud';
  hud.style.cssText = `
    position: fixed; top: 60px; right: 20px; z-index: 9999;
    padding: 12px 18px; background: rgba(15, 23, 42, 0.85); backdrop-filter: blur(8px);
    border: 1px solid rgba(102, 126, 234, 0.3); border-radius: 12px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4); color: white;
    font-family: 'Segoe UI', system-ui, sans-serif; display: flex; flex-direction: column;
    gap: 6px; min-width: 200px; transition: all 0.3s ease; pointer-events: none;
    opacity: 0; transform: translateY(-10px);
  `;
  const row = document.createElement('div');
  row.style.cssText = "display: flex; align-items: center; justify-content: space-between; gap: 10px;";

  const statusGroup = document.createElement('div');
  statusGroup.style.cssText = "display: flex; align-items: center; gap: 8px;";

  const indicator = document.createElement('div');
  indicator.id = 'hud-indicator';
  indicator.style.cssText = "width: 8px; height: 8px; border-radius: 50%; background: #667eea; box-shadow: 0 0 10px #667eea; animation: pulse-hud 2s infinite;";

  const status = document.createElement('span');
  status.id = 'hud-status';
  status.style.cssText = "font-size: 13px; font-weight: 600; color: #e2e8f0;";
  status.textContent = 'Ready';

  statusGroup.appendChild(indicator);
  statusGroup.appendChild(status);

  const timer = document.createElement('span');
  timer.id = 'hud-timer';
  timer.style.cssText = "font-size: 12px; font-family: monospace; color: #94a3b8;";
  timer.textContent = '00:00';

  row.appendChild(statusGroup);
  row.appendChild(timer);

  const progressContainer = document.createElement('div');
  progressContainer.style.cssText = "width: 100%; height: 4px; background: rgba(255,255,255,0.1); border-radius: 2px; overflow: hidden; margin-top: 4px;";

  const progress = document.createElement('div');
  progress.id = 'hud-progress';
  progress.style.cssText = "width: 0%; height: 100%; background: #667eea; transition: width 0.3s ease;";

  progressContainer.appendChild(progress);

  hud.appendChild(row);
  hud.appendChild(progressContainer);

  const style = document.createElement('style');
  style.textContent = `@keyframes pulse-hud { 0%, 100% { opacity: 0.5; transform: scale(0.9); } 50% { opacity: 1; transform: scale(1.1); } }`;
  document.head.appendChild(style);
  document.body.appendChild(hud);
}

function updateHUD(status, color = "#667eea", progress = 0) {
  createHUD();
  const hud = document.getElementById('lc-nvidia-hud');
  const statusEl = document.getElementById('hud-status');
  const indicatorEl = document.getElementById('hud-indicator');
  const progressEl = document.getElementById('hud-progress');
  if (hud) { hud.style.opacity = "1"; hud.style.transform = "translateY(0)"; }
  if (statusEl) statusEl.innerText = status;
  if (indicatorEl) { indicatorEl.style.background = color; indicatorEl.style.color = color; }
  if (progressEl) progressEl.style.width = `${progress}%`;
}

function startTimer(duration = 0) {
  stopTimer(); startTime = Date.now(); countdownDuration = duration;
  const timerEl = document.getElementById('hud-timer');
  timerInterval = setInterval(() => {
    let elapsed = Math.floor((Date.now() - startTime) / 1000);
    
    // Always countdown if duration > 0, otherwise count up (only for idle/success)
    let displayTime = countdownDuration > 0 ? Math.max(0, countdownDuration - elapsed) : elapsed;
    
    const mins = Math.floor(displayTime / 60).toString().padStart(2, '0');
    const secs = (displayTime % 60).toString().padStart(2, '0');
    if (timerEl) timerEl.innerText = `${mins}:${secs}`;
    
    // WATCHDOG: If active countdown hits 0 (plus 2s margin), force a failover
    if (countdownDuration > 0 && displayTime === 0 && elapsed > (countdownDuration + 2)) {
        console.warn("Watchdog: Model timeout detected. Rotating...");
        stopTimer();
        const controller = window._lc_controller;
        if (controller) controller.abort(); // Triggers the .catch() in triggerSolve
    }
  }, 1000);
}

function stopTimer() { 
    clearInterval(timerInterval); 
    const timerEl = document.getElementById('hud-timer');
    if (timerEl) timerEl.innerText = "00:00";
}

function hideHUDIn(ms = 3000) {
  setTimeout(() => {
    const hud = document.getElementById('lc-nvidia-hud');
    if (hud && !isTesting && !isSubmitting && !autoMode) { hud.style.opacity = "0"; hud.style.transform = "translateY(-10px)"; }
  }, ms);
}

// ===================== STATE SYNC =====================

chrome.storage.local.get(['autoMode'], (result) => {
  autoMode = !!result.autoMode;
  fetch(`${BACKEND_URL}/health`).then(r => r.json()).then(data => { if (data.models) modelList = data.models; });
  if (autoMode) { createHUD(); updateHUD("⚡ Quick-Init...", "#667eea", 15); setTimeout(startAutoSolve, 1000); }
});

chrome.storage.onChanged.addListener((changes) => {
  if (changes.autoMode) {
    autoMode = changes.autoMode.newValue;
    if (autoMode) { createHUD(); updateHUD("🚀 Turbo Start", "#667eea", 25); setTimeout(startAutoSolve, 500); }
    else { updateHUD("💤 Auto OFF", "#94a3b8", 0); hideHUDIn(2000); }
  }
});

// ===================== SCRAPING =====================
function findButtonByText(possibleTexts) {
  return Array.from(document.querySelectorAll('button, a')).find(el => {
    const text = (el.innerText || el.textContent || "").toLowerCase().trim();
    return possibleTexts.some(pt => text === pt.toLowerCase() || (text.includes(pt.toLowerCase()) && text.length < 15));
  });
}

function getProblemTitle() {
  const el = document.querySelector('[data-cy="question-title"]') || document.querySelector('div[class*="text-title-large"]');
  if (el && el.innerText.trim()) return el.innerText.trim();
  
  const h1 = document.querySelector('h1') || document.querySelector('h3');
  if (h1 && h1.innerText.trim()) return h1.innerText.trim();
  
  if (document.title) {
    const titleParts = document.title.split(' - ');
    if (titleParts.length > 0 && titleParts[0].trim()) {
      return titleParts[0].trim();
    }
  }
  return "Unknown Problem";
}

function getProblemDescription() {
  const selectors = [
    '[data-track-load="description_content"]',
    'div[class*="elfjS"]',
    '.question-content',
    '.question-description',
    'div[class*="question-content"]',
    'div[class*="question-description"]'
  ];
  for (const selector of selectors) {
    const el = document.querySelector(selector);
    if (el && el.innerText.trim()) return el.innerText.trim();
  }
  return "No desc found";
}

function detectResultState() {
  const selectors = [
    '[data-e2e-locator="console-result"]',
    'div[class*="result"]',
    'div[class*="console-result"]',
    'div[class*="status"]',
    '[class*="result-state"]'
  ];
  let text = "";
  for (const selector of selectors) {
    const el = document.querySelector(selector);
    if (el && el.innerText.trim()) {
      text += " " + el.innerText.trim();
    }
  }
  const pageText = document.body.innerText;
  const fullText = (text + " " + pageText);
  
  if (fullText.includes("Accepted") || fullText.includes("Success") || fullText.includes("Solved!")) return "accepted";
  if (fullText.includes("Compile Error")) return "compile_error";
  if (fullText.includes("Wrong Answer")) return "wrong_answer";
  if (fullText.includes("Runtime Error")) return "runtime_error";
  if (fullText.includes("Time Limit")) return "tle";
  if (fullText.includes("Memory Limit")) return "mle";
  if (fullText.includes("submitting too frequently")) return "rate_limit_lc";
  return null;
}

// ===================== AUTOMATION =====================

function startAutoSolve() { if (autoMode) { closeSidebars(); const btn = document.getElementById('lc-solve-ai-btn'); if (btn && !btn.disabled) btn.click(); } }

async function handleAutoPhase() {
  if (!autoMode) return;
  const state = detectResultState();
  if (!state) return;

  if (state === "accepted") {
    if (isTesting) {
      updateHUD("🧪 Test OK! Submitting...", "#4cd137", 80);
      isTesting = false; isSubmitting = true; isWaitingFinal = true;
      setTimeout(clickSubmitButton, 1000); // Wait for modal load
    } else if (isWaitingFinal) {
      // Ensure we see a "Success" specifically after submitting
      const successText = document.body.innerText;
      if (successText.includes("Accepted") || successText.includes("Success") || successText.includes("Solved!")) {
          stopTimer(); updateHUD("🏁 Solved! Move...", "#4cd137", 100);
          isSubmitting = false; isHandlingError = false; isWaitingFinal = false; fixAttempts = 0;
          setTimeout(navigateToNext, 1000);
      }
    }
    return;
  }

  if (state === "rate_limit_lc") {
    if (isWaitingLC) return;
    isWaitingLC = true;
    const wasTesting = isTesting; const wasSubmitting = isSubmitting;
    isTesting = false; isSubmitting = false;
    updateHUD("⏳ LC Rate Limit (8s Wait)", "#fbc531", 100);
    stopTimer();
    setTimeout(() => {
        isWaitingLC = false;
        if (wasTesting) clickRunButton();
        else if (wasSubmitting) clickSubmitButton();
        else startAutoSolve();
    }, 8000); // 8 second cooldown as requested
    return;
  }

  // Handle Errors during Testing/Submitting
  if (state && state !== "accepted" && !isHandlingError) {
    if (fixAttempts >= MAX_FIX_ATTEMPTS) {
      stopTimer(); 
      updateHUD("❌ Skipping (Retry Limit)", "#e84118", 100);
      setTimeout(navigateToNext, 2000); // Wait 2s to show failure status then skip
      return;
    }
    isHandlingError = true; isTesting = false; isSubmitting = false;
    const resultArea = document.querySelector('[data-e2e-locator="console-result"]') || document.querySelector('div[class*="result"]');
    const error_text = resultArea?.innerText.substring(0, 1500) || "Unknown error";
    updateHUD(`🔧 Repairing (${state})`, "#fbc531", 60); fixAttempts++;
    triggerSolve({ error_text, is_logic_error: state === "wrong_answer" });
  }
}

function simulateNextHotkey() {
    // Simulate LeetCode's Ctrl + Right Arrow shortcut
    const eventParams = { key: 'ArrowRight', keyCode: 39, code: 'ArrowRight', ctrlKey: true, bubbles: true, cancelable: true };
    document.dispatchEvent(new KeyboardEvent('keydown', eventParams));
    document.dispatchEvent(new KeyboardEvent('keyup', eventParams));
}

function navigateToNext() {
  updateHUD("⏩ Next unsolved...", "#764ba2", 0);
  setTimeout(() => {
    isTesting = false; isSubmitting = false; isHandlingError = false; fixAttempts = 0;
    
    // Attempt 1: Shortcut Key (Fastest in background)
    simulateNextHotkey();

    // Attempt 2: Smart Search in Sidebar (Fallback)
    setTimeout(() => {
        const items = Array.from(document.querySelectorAll('div[class*="flex"]')).filter(el => 
            el.innerText.match(/^\d+\./) || el.parentElement?.innerText.match(/^\d+\./)
        );
        
        if (items.length > 0) {
            const nextUnsolved = items.find(el => {
                const hasCheck = !!el.querySelector('svg[class*="text-green"]') || el.innerHTML.includes('check-circle');
                return !hasCheck;
            });
            
            if (nextUnsolved) {
                console.log("Smart Nav: Found unsolved problem", nextUnsolved.innerText);
                nextUnsolved.click();
                return;
            }
        }

        // Attempt 3: Fallback to Standard Selectors
        const selectors = [
            'button[aria-label="next question"]',
            'button[aria-label="Next Question"]',
            '[data-cy="next-question-btn"]',
            '.next-question-btn',
            'a[href*="/problems/"] svg[viewBox*="right"]',
            'button svg[viewBox*="right"]'
        ];
        
        let nextBtn = null;
        for (const selector of selectors) {
            nextBtn = document.querySelector(selector);
            if (nextBtn) {
                if (nextBtn.tagName === 'svg') nextBtn = nextBtn.closest('button') || nextBtn.closest('a');
                break;
            }
        }

        if (nextBtn) {
            console.log("Navigating via button...");
            nextBtn.click();
        } else {
            // Last resort: If still on same page, maybe shortcut didn't work, try button directly by text
            const btn = Array.from(document.querySelectorAll('button, a')).find(b => 
                b.innerText.toLowerCase().includes('next question') || 
                b.innerText.toLowerCase().includes('next') && b.innerText.length < 10
            );
            if (btn) btn.click();
        }
    }, 500);
  }, 1000); 
}

// ===================== CORE ACTIONS =====================

function closeSidebars() {
    // Selectors for common LeetCode sidebars/drawers (Daily Question, etc.)
    const closeSelectors = [
        'button[aria-label="close"]',
        'button[aria-label="Close"]',
        'div[class*="drawer"] button',
        'div[class*="sidebar"] button[class*="close"]'
    ];
    
    closeSelectors.forEach(selector => {
        const btn = document.querySelector(selector);
        if (btn && btn.offsetParent !== null) { // If visible
            btn.click();
            console.log("Auto-closed sidebar for clarity");
        }
    });

    // Also look for the 'X' icon specifically if aria-label is missing
    const xButtons = Array.from(document.querySelectorAll('button')).filter(b => {
        const svg = b.querySelector('svg');
        return svg && (svg.innerHTML.includes('M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z') || svg.getAttribute('viewBox') === '0 0 24 24');
    });
    xButtons.forEach(btn => { if (btn.offsetParent !== null) btn.click(); });
}

async function triggerSolve(extraParams = {}) {
  const btn = document.getElementById('lc-solve-ai-btn'); if (!btn) return;
  const isFix = !!extraParams.error_text;
  
  // Model Rotation Logic: Sequential Fallback (Index-based)
  let modelIdx = null;
  let modelName = "AI";
  if (modelList.length > 0) {
      modelIdx = fixAttempts % modelList.length;
      modelName = modelList[modelIdx].split('/').pop().split('-')[0]; // Short name e.g. "qwen" or "minimax"
      extraParams.model_index = modelIdx;
  }

  btn.innerText = isFix ? `🔧 Fixing (${modelName})...` : `⌛ Solving (${modelName})...`; 
  btn.disabled = true;
  updateHUD(isFix ? `🔧 Fixing (${modelName})...` : `🧠 Thinking (${modelName})...`, "#667eea", 40); 
  startTimer(45); 
  window.postMessage({ type: "GET_EDITOR_VALUE" }, "*");
  const onMessage = async (event) => {
    if (event.data.type === "EDITOR_VALUE_RETURN") {
      window.removeEventListener("message", onMessage);
      try {
        const controller = new AbortController();
        window._lc_controller = controller; // Store globally for watchdog
        const timeoutId = setTimeout(() => controller.abort(), 50000); // 50s fetch timeout
        
        const response = await fetch(`${BACKEND_URL}/solve`, { 
            method: 'POST', 
            headers: { 'Content-Type': 'application/json' }, 
            signal: controller.signal,
            body: JSON.stringify({ 
                title: getProblemTitle(), 
                description: getProblemDescription(), 
                boilerplate: event.data.value, 
                language: event.data.language || "cpp",
                ...extraParams 
            }) 
        });
        clearTimeout(timeoutId);
        
        const data = await response.json();
        if (data.success) {
          window.postMessage({ type: "SET_EDITOR_VALUE", value: data.code }, "*");
          btn.innerText = '✅ Code Ready'; isHandlingError = false;
          if (autoMode) { updateHUD("📝 Injecting...", "#667eea", 70); isTesting = true; setTimeout(clickRunButton, 500); }
          else { stopTimer(); updateHUD("✅ Done!", "#4cd137", 100); hideHUDIn(3000); }
        } else { 
          stopTimer(); 
          const errorMsg = data.error || "AI Failed";
          const isTimeout = errorMsg.toLowerCase().includes("timeout");
          
          if (isTimeout && autoMode) {
              updateHUD("⏳ Timeout (Rotating...)", "#fbc531", 100);
              fixAttempts++; // Force rotation
              isHandlingError = false;
              setTimeout(() => triggerSolve(extraParams), 1000); // RESTART on timeout
              return;
          }

          if (data.is_rate_limit) {
            updateHUD("⏳ Rate Limited (Wait 5s)", "#fbc531", 100);
            fixAttempts++; // Force rotation on rate limit
            if (autoMode) { setTimeout(() => triggerSolve(extraParams), 5000); return; } 
          } else {
            updateHUD(`❌ ${errorMsg}`, "#e84118", 100); 
          }
          isHandlingError = false; 
        }
      } catch (err) { 
        stopTimer(); 
        const isTimeout = err.name === 'AbortError';
        updateHUD(isTimeout ? "⏳ Timeout (Switching...)" : "❌ Error (Retrying...)", "#fbc531", 100); 
        fixAttempts++; // Move to next model
        isHandlingError = false; 
        
        // AUTO-RETRY: If in auto-mode, immediately trigger the NEXT model in the list
        if (autoMode) {
            console.log(`Auto-Failover: ${isTimeout ? 'Timeout' : 'Error'} occurred. Moving to next model...`);
            setTimeout(() => triggerSolve(extraParams), 1000); 
        }
      }
      btn.disabled = false;
    }
  };
  window.addEventListener("message", onMessage);
}

function clickRunButton() {
  let runBtn = document.querySelector('[data-e2e-locator="console-run-button"]') || document.querySelector('button[data-cy="run-code-btn"]');
  if (!runBtn) {
    runBtn = findButtonByText(["Run", "Run Code"]);
  }
  if (runBtn) { updateHUD("🧪 Testing...", "#fbc531", 75); isTesting = true; isSubmitting = false; startTimer(25); runBtn.click(); }
}

function clickSubmitButton() {
  let submitBtn = document.querySelector('[data-e2e-locator="console-submit-button"]') || document.querySelector('button[data-cy="submit-code-btn"]');
  if (!submitBtn) {
    submitBtn = findButtonByText(["Submit", "Submit Code"]);
  }
  if (submitBtn) { updateHUD("🚀 Final Submit...", "#4cd137", 90); isTesting = false; isSubmitting = true; isWaitingFinal = true; startTimer(25); submitBtn.click(); }
}

function injectButton() {
  if (document.getElementById('lc-solve-ai-btn')) return;
  const target = document.querySelector('[class*="Navbar"] [class*="flex items-center"]') || document.querySelector('[class*="action__"]') || document.querySelector('div[class*="flex items-center"]');
  if (!target) return;
  const btn = document.createElement('button'); btn.id = 'lc-solve-ai-btn'; btn.innerText = '🤖 AI Solve';
  btn.style.cssText = `margin-left: 8px; height: 28px; padding: 0 10px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; border-radius: 4px; font-weight: 600; font-size: 11px; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; white-space: nowrap; transition: all 0.2s ease; vertical-align: middle;`;
  btn.onclick = () => triggerSolve(); target.appendChild(btn);
}

const script = document.createElement('script'); script.src = chrome.runtime.getURL('injected.js'); (document.head || document.documentElement).appendChild(script);
setInterval(injectButton, 2000);
setInterval(() => { if (autoMode) closeSidebars(); }, 3000); // Aggressive UI cleanup
const observer = new MutationObserver(() => { if (autoMode && !isHandlingError) setTimeout(handleAutoPhase, 500); });
observer.observe(document.body, { childList: true, subtree: true });
let lastUrl = location.href;
new MutationObserver(() => {
  if (location.href !== lastUrl) { lastUrl = location.href; fixAttempts = 0; isHandlingError = false; isTesting = false; isSubmitting = false; stopTimer(); closeSidebars(); updateHUD("🆕 New Load...", "#667eea", 25); setTimeout(startAutoSolve, 1000); }
}).observe(document, { subtree: true, childList: true });
