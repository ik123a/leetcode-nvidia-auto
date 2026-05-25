import os
import sys
import time
import json
import urllib.request
import urllib.error
from datetime import datetime
from playwright.sync_api import sync_playwright

# Fix Windows console encoding for emoji/unicode in logs
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

BACKEND_URL = "http://127.0.0.1:5050"
KNOWLEDGE_FILE = os.path.join(os.path.dirname(__file__), "solver_knowledge.json")

# ============================================================
#  KNOWLEDGE FILE: Shared memory across all models
# ============================================================

def load_knowledge():
    """Load the shared knowledge file. Returns dict."""
    if os.path.exists(KNOWLEDGE_FILE):
        try:
            with open(KNOWLEDGE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def save_knowledge(knowledge):
    """Save knowledge to disk."""
    try:
        with open(KNOWLEDGE_FILE, 'w', encoding='utf-8') as f:
            json.dump(knowledge, f, indent=2, ensure_ascii=False)
    except IOError as e:
        print(f"  [WARN] Could not save knowledge: {e}")


def get_slug(url):
    """Extract problem slug from LeetCode URL."""
    # https://leetcode.com/problems/two-sum/ -> two-sum
    try:
        parts = url.rstrip('/').split('/problems/')
        if len(parts) > 1:
            slug = parts[1].split('/')[0]
            return slug
    except:
        pass
    return None


def record_attempt(knowledge, slug, title, model, code, result, error_text="",
                   input_data="", expected_output="", actual_output="", language="cpp"):
    """Record a failed attempt into the knowledge file."""
    if slug not in knowledge:
        knowledge[slug] = {
            "title": title,
            "attempts": [],
            "solved": False,
            "solution": None,
            "solve_model": None,
            "language": language
        }
    knowledge[slug]["attempts"].append({
        "model": model,
        "language": language,
        "code": code[:3000],  # Truncate to keep file manageable
        "result": result,
        "error_text": str(error_text)[:500],
        "input_data": str(input_data)[:300],
        "expected_output": str(expected_output)[:300],
        "actual_output": str(actual_output)[:300],
        "timestamp": datetime.now().isoformat()
    })
    save_knowledge(knowledge)


def mark_solved(knowledge, slug, model, code, language="cpp"):
    """Mark a problem as solved in the knowledge file."""
    if slug not in knowledge:
        knowledge[slug] = {"title": slug, "attempts": [], "solved": False, "solution": None, "solve_model": None, "language": language}
    knowledge[slug]["solved"] = True
    knowledge[slug]["solution"] = code[:3000]
    knowledge[slug]["solve_model"] = model
    knowledge[slug]["language"] = language
    save_knowledge(knowledge)


# ============================================================
#  BACKEND COMMUNICATION
# ============================================================

def get_models():
    """Fetch available models from backend."""
    try:
        req = urllib.request.Request(f"{BACKEND_URL}/models", method='GET')
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data.get('models', [])
    except Exception as e:
        print(f"  [WARN] Could not fetch models: {e}")
        # Fallback hardcoded list
        return [
            "deepseek-ai/deepseek-v3.2",
            "qwen/qwen3-coder-480b-a35b-instruct",
            "nvidia/llama-3.1-nemotron-ultra-253b-v1",
            "qwen/qwen3.5-397b-a17b",
            "qwen/qwen2.5-coder-32b-instruct",
        ]


def fetch_solution_evolve(problem_data, model_name, previous_attempts):
    """Call the /solve_evolve endpoint with history context."""
    payload = {
        "title": problem_data["title"],
        "description": problem_data["description"],
        "boilerplate": problem_data["boilerplate"],
        "language": problem_data.get("language", "cpp"),
        "model_name": model_name,
        "previous_attempts": previous_attempts
    }
    req = urllib.request.Request(
        f"{BACKEND_URL}/solve_evolve",
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            data = json.loads(response.read().decode('utf-8'))
            if data.get('success'):
                return data.get('code'), data.get('model')
            print(f"    [Backend error]: {data.get('error')}")
            return None, model_name
    except Exception as e:
        print(f"    [Backend exception]: {e}")
        return None, model_name


# ============================================================
#  PAGE INTERACTION HELPERS
# ============================================================

def dismiss_overlays(page):
    """Dismiss any overlays/toasts."""
    try:
        page.evaluate('''() => {
            document.querySelectorAll('[role="alert"], [class*="toast"], [class*="Toastify"], [class*="notification"]').forEach(el => {
                try { el.remove(); } catch(e) {}
            });
        }''')
    except:
        pass


def go_next(page):
    """Navigate to next problem. Try everything, never fail."""
    dismiss_overlays(page)

    # Try DOM next button
    try:
        clicked = page.evaluate('''() => {
            for (const s of ['button[aria-label="next question"]', 'button[aria-label="Next Question"]', '[data-cy="next-question-btn"]']) {
                const b = document.querySelector(s);
                if (b && b.offsetParent !== null) { b.click(); return true; }
            }
            return false;
        }''')
        if clicked:
            page.wait_for_timeout(4000)
            return
    except:
        pass

    # Try keyboard shortcut
    try:
        page.evaluate("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowRight', keyCode: 39, ctrlKey: true, bubbles: true}));")
        page.wait_for_timeout(4000)
        return
    except:
        pass

    # Last resort: go to random problem
    try:
        page.goto("https://leetcode.com/problems/random-one-question/all", timeout=15000)
        page.wait_for_timeout(5000)
    except:
        pass


def quick_poll(page, max_secs=20):
    """
    Poll console result. Returns dict with structured info.
    Returns: {"status": "accepted"|"error"|"skip", "error_type": ..., "details": ...}
    """
    for _ in range(max_secs):
        page.wait_for_timeout(1000)
        try:
            txt = page.evaluate('''() => {
                const selectors = [
                    '[data-e2e-locator="console-result"]',
                    'div[class*="result"]',
                    'div[class*="console-result"]',
                    'div[class*="status"]',
                    '[class*="result-state"]'
                ];
                let full = "";
                for (const s of selectors) {
                    const el = document.querySelector(s);
                    if (el && el.innerText.trim()) {
                        full += " " + el.innerText.trim();
                    }
                }
                return full || document.body.innerText;
            }''')
        except:
            return {"status": "skip", "error_type": "page_error", "details": ""}

        if not txt:
            # Check for 404/error toast
            try:
                has_err = page.evaluate('''() => {
                    const alerts = document.querySelectorAll('[role="alert"], [class*="toast"], [class*="Toastify"]');
                    for (const el of alerts) {
                        if ((el.textContent || "").includes("404") || (el.textContent || "").includes("Not Found")) return true;
                    }
                    return false;
                }''')
                if has_err:
                    return {"status": "skip", "error_type": "404", "details": ""}
            except:
                pass
            continue

        if "Accepted" in txt or "Success" in txt:
            return {"status": "accepted", "error_type": "", "details": txt}
        if "Compile Error" in txt:
            return {"status": "error", "error_type": "Compile Error", "details": txt}
        if "Runtime Error" in txt:
            return {"status": "error", "error_type": "Runtime Error", "details": txt}
        if "Wrong Answer" in txt:
            return {"status": "error", "error_type": "Wrong Answer", "details": txt}
        if "Limit Exceeded" in txt:
            return {"status": "error", "error_type": "Time/Memory Limit Exceeded", "details": txt}
        if "submitting too frequently" in txt.lower():
            return {"status": "skip", "error_type": "rate_limit", "details": txt}

    return {"status": "skip", "error_type": "timeout", "details": ""}


def extract_error_details(page):
    """Extract detailed error info from the console (input/output/expected for Wrong Answer, etc.)."""
    try:
        details = page.evaluate('''() => {
            const result = {};
            // Try different selector patterns for console results
            const outputEl = document.querySelector('[data-e2e-locator="console-result"]') || document.querySelector('div[class*="result"]');
            if (outputEl) result.full_text = outputEl.innerText;

            // Try to find input/output/expected sections
            const allPres = document.querySelectorAll('.font-menlo, pre, [class*="view-lines"]');
            const texts = [];
            allPres.forEach(el => {
                const t = el.innerText || el.textContent;
                if (t && t.trim()) texts.push(t.trim());
            });
            result.raw_texts = texts.slice(0, 6);

            // Try specific LeetCode elements
            const inputEl = document.querySelector('[data-e2e-locator="console-testcase-input"]');
            if (inputEl) result.input = inputEl.innerText || inputEl.textContent;

            const stdoutEl = document.querySelector('[data-e2e-locator="console-stdout"]');
            if (stdoutEl) result.stdout = stdoutEl.innerText || stdoutEl.textContent;

            return result;
        }''')
        return details
    except:
        return {}


def inject_and_run(page, code):
    """Inject code into Monaco editor, trigger change detection, and click Run."""
    # Inject code
    try:
        page.evaluate('''([code]) => {
            const editor = monaco.editor.getEditors()[0];
            editor.executeEdits("bot", [{ range: editor.getModel().getFullModelRange(), text: code }]);
        }''', [code])
    except:
        return False

    page.wait_for_timeout(500)

    # Trigger Monaco change detection
    try:
        page.locator('.inputarea').first.focus()
        page.keyboard.press("Space")
        page.wait_for_timeout(100)
        page.keyboard.press("Backspace")
    except:
        pass
    page.wait_for_timeout(1000)

    # Click Run
    try:
        run_ok = page.evaluate('''() => {
            let btn = document.querySelector('[data-e2e-locator="console-run-button"]') || document.querySelector('button[data-cy="run-code-btn"]');
            if (!btn) {
                btn = Array.from(document.querySelectorAll('button, a')).find(el => {
                    const t = (el.innerText || el.textContent || "").toLowerCase().trim();
                    return t === "run" || (t.includes("run") && t.length < 15);
                });
            }
            if (btn) { btn.click(); return true; }
            return false;
        }''')
        return run_ok
    except:
        return False


def click_submit(page):
    """Click the submit button."""
    try:
        page.evaluate('''() => {
            let btn = document.querySelector('[data-e2e-locator="console-submit-button"]') || document.querySelector('button[data-cy="submit-code-btn"]');
            if (!btn) {
                btn = Array.from(document.querySelectorAll('button, a')).find(el => {
                    const t = (el.innerText || el.textContent || "").toLowerCase().trim();
                    return t === "submit" || (t.includes("submit") && t.length < 15);
                });
            }
            if (btn) { btn.click(); return true; }
            return false;
        }''')
        return True
    except:
        return False


def extract_problem(page):
    """Extract problem title, description, boilerplate, and language from the current page."""
    try:
        page.wait_for_selector('[data-cy="question-title"], div[class*="text-title-large"], h1, h3', timeout=8000)
    except:
        pass

    title = page.evaluate('''() => {
        const el = document.querySelector('[data-cy="question-title"]') || document.querySelector('div[class*="text-title-large"]');
        if (el && el.innerText.trim()) return el.innerText.trim();
        const h1 = document.querySelector('h1') || document.querySelector('h3');
        if (h1 && h1.innerText.trim()) return h1.innerText.trim();
        if (document.title) {
            const parts = document.title.split(' - ');
            if (parts.length > 0 && parts[0].trim()) return parts[0].trim();
        }
        return null;
    }''')

    desc = page.evaluate('''() => {
        const selectors = [
            '[data-track-load="description_content"]',
            'div[class*="elfjS"]',
            '.question-content',
            '.question-description',
            'div[class*="question-content"]',
            'div[class*="question-description"]'
        ];
        for (const s of selectors) {
            const el = document.querySelector(s);
            if (el && el.innerText.trim()) return el.innerText.trim();
        }
        return null;
    }''')

    editor_data = page.evaluate('''() => {
        return new Promise((resolve) => {
            let r = 0;
            const i = setInterval(() => {
                if (typeof monaco !== "undefined" && monaco.editor && monaco.editor.getEditors().length > 0) {
                    clearInterval(i);
                    const editor = monaco.editor.getEditors()[0];
                    resolve({
                        boilerplate: editor.getValue(),
                        language: editor.getModel() ? editor.getModel().getLanguageId() : "cpp"
                    });
                }
                if (++r > 12) { clearInterval(i); resolve(null); }
            }, 500);
        });
    }''')

    boilerplate = editor_data.get('boilerplate') if editor_data else None
    language = editor_data.get('language') if editor_data else 'cpp'

    return title, desc, boilerplate, language


# ============================================================
#  MAIN: NEVER-SKIP SOLVER WITH MULTI-MODEL EVOLUTION
# ============================================================

def main():
    print("=" * 60)
    print("  LeetCode Bot - MULTI-MODEL EVOLUTION SOLVER")
    print("  Every question. Every model. Never skip.")
    print("=" * 60)

    # Load shared knowledge
    knowledge = load_knowledge()
    already_solved = sum(1 for v in knowledge.values() if v.get('solved'))
    print(f"\n  Knowledge file: {len(knowledge)} problems tracked, {already_solved} already solved")

    # Fetch available models
    MODELS = get_models()
    print(f"  Available models: {len(MODELS)}")
    for i, m in enumerate(MODELS):
        print(f"    [{i}] {m}")

    with sync_playwright() as p:
        user_data_dir = os.path.join(os.getcwd(), 'chrome_data')
        browser = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,
            args=["--start-maximized"]
        )

        page = browser.pages[0] if browser.pages else browser.new_page()
        page.set_default_timeout(12000)
        page.set_default_navigation_timeout(20000)

        page.goto("https://leetcode.com/problems/two-sum/")

        print("\n>>> Log in to LeetCode. Bot starts in 15 seconds... <<<\n")
        page.wait_for_timeout(15000)

        solved_count = 0
        failed_slugs = []  # Track unsolved problems for second pass
        question_num = 0

        # ==================== PASS 1: SEQUENTIAL ====================
        print("\n" + "=" * 60)
        print("  PASS 1: Solving problems sequentially")
        print("=" * 60)

        while True:
            question_num += 1
            current_url = page.url
            slug = get_slug(current_url)

            try:
                print(f"\n{'─' * 50}")
                print(f"  [Q#{question_num}] {current_url}")

                # Skip submissions pages
                if "/submissions/" in current_url:
                    print("  -> submissions page, navigating next...")
                    go_next(page)
                    continue

                # Check if already solved in knowledge
                if slug and knowledge.get(slug, {}).get('solved'):
                    print(f"  -> Already solved ({slug}), next...")
                    go_next(page)
                    continue

                page.wait_for_timeout(3000)

                # Extract problem
                title, desc, boilerplate, language = extract_problem(page)

                if not title or not desc:
                    print("  -> Missing title/description, next...")
                    go_next(page)
                    continue

                if not boilerplate:
                    print("  -> No editor found, next...")
                    go_next(page)
                    continue

                print(f"  -> Problem: {title} (Language: {language})")

                problem_data = {
                    "title": title,
                    "description": desc,
                    "boilerplate": boilerplate,
                    "language": language
                }

                # Build previous attempts from knowledge file
                prev_attempts = []
                if slug and slug in knowledge:
                    prev_attempts = knowledge[slug].get("attempts", [])

                # ===== TRY EACH MODEL SEQUENTIALLY =====
                problem_solved = False

                for model_idx, model_name in enumerate(MODELS):
                    model_short = model_name.split('/')[-1][:30]
                    print(f"\n    [{model_idx+1}/{len(MODELS)}] Trying: {model_short}")
                    print(f"    Previous failures fed to this model: {len(prev_attempts)}")

                    # Ask backend for solution (with evolution context)
                    code, used_model = fetch_solution_evolve(problem_data, model_name, prev_attempts)

                    if not code or len(code.strip()) < 10:
                        print(f"    -> Bad/empty code from {model_short}")
                        record_attempt(knowledge, slug or f"unknown-{question_num}", title,
                                      model_name, "", "API Failed", "No code returned", language=language)
                        prev_attempts = knowledge.get(slug or f"unknown-{question_num}", {}).get("attempts", [])
                        continue

                    # Inject and Run
                    print(f"    -> Injecting code ({len(code)} chars)...")
                    if not inject_and_run(page, code):
                        print(f"    -> Inject/Run failed")
                        record_attempt(knowledge, slug or f"unknown-{question_num}", title,
                                      model_name, code, "Inject Failed", "Could not inject or run", language=language)
                        prev_attempts = knowledge.get(slug or f"unknown-{question_num}", {}).get("attempts", [])
                        continue

                    # Wait for result
                    print(f"    -> Running tests...")
                    run_result = quick_poll(page, 20)

                    if run_result["status"] == "accepted":
                        # Tests passed! Submit!
                        print(f"    -> ✅ Tests PASSED! Submitting...")
                        page.wait_for_timeout(1000)

                        if not click_submit(page):
                            print(f"    -> Submit button failed, trying next model")
                            continue

                        sub_result = quick_poll(page, 20)

                        if sub_result["status"] == "accepted":
                            print(f"    -> 🏆 SOLVED by {model_short}!")
                            solved_count += 1
                            mark_solved(knowledge, slug or f"unknown-{question_num}", model_name, code, language=language)
                            problem_solved = True
                            page.wait_for_timeout(2000)
                            break
                        else:
                            # Passed run but failed submit (edge case: TLE on full test suite)
                            print(f"    -> Submit failed: {sub_result['error_type']}")
                            error_details = extract_error_details(page)
                            record_attempt(knowledge, slug or f"unknown-{question_num}", title,
                                          model_name, code, f"Submit: {sub_result['error_type']}",
                                          sub_result.get('details', ''),
                                          error_details.get('input', ''),
                                          error_details.get('raw_texts', [''])[0] if error_details.get('raw_texts') else '',
                                          '', language=language)
                            prev_attempts = knowledge.get(slug or f"unknown-{question_num}", {}).get("attempts", [])
                            # Wait a bit before trying next model (avoid rate limiting)
                            page.wait_for_timeout(2000)

                    elif run_result["status"] == "error":
                        # Test failed — record with details and try next model
                        print(f"    -> ❌ {run_result['error_type']}")
                        error_details = extract_error_details(page)
                        error_text = run_result.get('details', '')
                        input_data = error_details.get('input', '')
                        raw = error_details.get('raw_texts', [])

                        record_attempt(knowledge, slug or f"unknown-{question_num}", title,
                                      model_name, code, run_result['error_type'],
                                      error_text,
                                      input_data,
                                      raw[1] if len(raw) > 1 else '',
                                      raw[0] if len(raw) > 0 else '', language=language)
                        prev_attempts = knowledge.get(slug or f"unknown-{question_num}", {}).get("attempts", [])
                        page.wait_for_timeout(1500)

                    else:
                        # Skip/timeout
                        print(f"    -> Skipped: {run_result['error_type']}")
                        record_attempt(knowledge, slug or f"unknown-{question_num}", title,
                                      model_name, code, f"Skip: {run_result['error_type']}", "", language=language)
                        prev_attempts = knowledge.get(slug or f"unknown-{question_num}", {}).get("attempts", [])

                if not problem_solved:
                    print(f"\n  ⚠️ ALL {len(MODELS)} MODELS FAILED on: {title}")
                    print(f"  -> Will retry in Pass 2")
                    if slug:
                        failed_slugs.append(slug)

                # Print running stats
                total_tracked = sum(1 for v in knowledge.values() if v.get('solved'))
                print(f"\n  📊 Stats: {total_tracked} solved total | {len(failed_slugs)} queued for retry")

            except Exception as e:
                print(f"  !! Unexpected error: {e}")

            # ===== ALWAYS MOVE TO NEXT QUESTION =====
            print("  -> ⏩ Moving to next question...")
            try:
                go_next(page)
            except:
                try:
                    page.goto("https://leetcode.com/problems/random-one-question/all", timeout=15000)
                    page.wait_for_timeout(5000)
                except:
                    pass

            # Safety: if we've gone through a LOT of questions (300+), start pass 2
            if question_num >= 300:
                print("\n  Reached 300 questions in Pass 1, starting Pass 2...")
                break

        # ==================== PASS 2: RETRY FAILED ====================
        if failed_slugs:
            print("\n" + "=" * 60)
            print(f"  PASS 2: Retrying {len(failed_slugs)} unsolved problems")
            print("=" * 60)

            for retry_idx, slug in enumerate(failed_slugs):
                try:
                    print(f"\n{'─' * 50}")
                    print(f"  [RETRY {retry_idx+1}/{len(failed_slugs)}] {slug}")

                    # Check if it got solved somehow (another instance?)
                    knowledge = load_knowledge()  # Reload fresh
                    if knowledge.get(slug, {}).get('solved'):
                        print(f"  -> Already solved in the meantime!")
                        continue

                    # Navigate to the problem
                    page.goto(f"https://leetcode.com/problems/{slug}/", timeout=20000)
                    page.wait_for_timeout(4000)

                    # Extract problem
                    title, desc, boilerplate, language = extract_problem(page)
                    if not title or not desc or not boilerplate:
                        print(f"  -> Could not load problem, skipping")
                        continue

                    problem_data = {
                        "title": title,
                        "description": desc,
                        "boilerplate": boilerplate,
                        "language": language
                    }

                    # Get ALL previous attempts from knowledge (from Pass 1)
                    prev_attempts = knowledge.get(slug, {}).get("attempts", [])
                    print(f"  -> {len(prev_attempts)} prior failures to learn from")

                    # Try all models again with accumulated knowledge
                    problem_solved = False

                    for model_idx, model_name in enumerate(MODELS):
                        model_short = model_name.split('/')[-1][:30]
                        print(f"\n    [RETRY {model_idx+1}/{len(MODELS)}] {model_short}")

                        code, used_model = fetch_solution_evolve(problem_data, model_name, prev_attempts)

                        if not code or len(code.strip()) < 10:
                            print(f"    -> Bad code")
                            continue

                        if not inject_and_run(page, code):
                            print(f"    -> Inject failed")
                            continue

                        print(f"    -> Running tests...")
                        run_result = quick_poll(page, 20)

                        if run_result["status"] == "accepted":
                            print(f"    -> ✅ Tests PASSED! Submitting...")
                            page.wait_for_timeout(1000)

                            if click_submit(page):
                                sub_result = quick_poll(page, 20)
                                if sub_result["status"] == "accepted":
                                    print(f"    -> 🏆 SOLVED on retry by {model_short}!")
                                    solved_count += 1
                                    mark_solved(knowledge, slug, model_name, code, language=language)
                                    problem_solved = True
                                    page.wait_for_timeout(2000)
                                    break
                                else:
                                    print(f"    -> Submit failed: {sub_result['error_type']}")
                                    error_details = extract_error_details(page)
                                    record_attempt(knowledge, slug, title, model_name, code,
                                                  f"Submit: {sub_result['error_type']}",
                                                  sub_result.get('details', ''), language=language)
                                    prev_attempts = knowledge.get(slug, {}).get("attempts", [])
                                    page.wait_for_timeout(2000)
                        elif run_result["status"] == "error":
                            print(f"    -> ❌ {run_result['error_type']}")
                            error_details = extract_error_details(page)
                            record_attempt(knowledge, slug, title, model_name, code,
                                          run_result['error_type'],
                                          run_result.get('details', ''),
                                          error_details.get('input', ''), language=language)
                            prev_attempts = knowledge.get(slug, {}).get("attempts", [])
                            page.wait_for_timeout(1500)
                        else:
                            print(f"    -> Skip: {run_result['error_type']}")

                    if not problem_solved:
                        print(f"\n  ❌ Still unsolved after Pass 2: {slug}")

                except Exception as e:
                    print(f"  !! Retry error: {e}")

        # ==================== FINAL REPORT ====================
        knowledge = load_knowledge()
        total_solved = sum(1 for v in knowledge.values() if v.get('solved'))
        total_tried = len(knowledge)
        unsolved = [k for k, v in knowledge.items() if not v.get('solved')]

        print("\n" + "=" * 60)
        print(f"  FINAL REPORT")
        print(f"  Total problems attempted: {total_tried}")
        print(f"  Total solved: {total_solved}")
        print(f"  Still unsolved: {len(unsolved)}")
        if unsolved:
            print(f"  Unsolved slugs: {', '.join(unsolved[:20])}")
            if len(unsolved) > 20:
                print(f"    ... and {len(unsolved) - 20} more")
        print("=" * 60)

        browser.close()


if __name__ == "__main__":
    main()
