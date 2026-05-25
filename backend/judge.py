import aiohttp
import os
import re
from dotenv import load_dotenv
from solvers import strip_markdown, get_language_name

load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")

# Smart routing URLs
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

# Judge uses Llama 3.3 70B (NVIDIA Hosted)
JUDGE_MODEL = "meta/llama-3.3-70b-instruct"
JUDGE_PROVIDER = "nvidia"  # "openrouter" or "nvidia"


async def judge_solutions(session, problem_data, results):
    """Deeply inspect and pick the best solution, adapting prompts to the active language."""
    if not results:
        return ""
    if len(results) == 1:
        return results[0]['code']

    language = problem_data.get('language', 'cpp')
    lang_name = get_language_name(language)

    solutions_text = ""
    for i, res in enumerate(results):
        solutions_text += f"\n--- CANDIDATE {i+1} ({res['model']}) ---\n{res['code']}\n"

    # Redefinition Check Guard per language
    bp = problem_data.get('boilerplate') or ""
    PROMPT_GUARD = ""
    if lang_name.lower() in ["c++", "cpp", "java", "c#", "csharp"]:
        if "ListNode" in bp or "TreeNode" in bp:
            PROMPT_GUARD = f"\nCRITICAL: Ensure the picked code DOES NOT redefine 'struct ListNode' or 'struct TreeNode'. LeetCode provides these objects globally.\n"
    elif lang_name.lower() in ["python", "python3"]:
        if "ListNode" in bp or "TreeNode" in bp:
            PROMPT_GUARD = f"\nCRITICAL: Ensure the picked code DOES NOT redefine classes 'ListNode' or 'TreeNode'. LeetCode imports these globally.\n"

    prompt = f"""Pick the BEST {lang_name} solution for '{problem_data['title']}'.{PROMPT_GUARD}

PROBLEM: {problem_data['description']}

CANDIDATES:{solutions_text}

Rules:
1. Pick the most correct+efficient solution.
2. Ensure full implementation (no empty bodies).
3. Return ONLY the complete fixed {lang_name} code in a ```{language} block.
4. NO explanations, NO intro/outro text.
"""

    # --- SMART ROUTING LAYER ---
    if JUDGE_PROVIDER == "nvidia":
        url = NVIDIA_URL
        key = NVIDIA_API_KEY
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        }
    else:
        url = OPENROUTER_URL
        key = OPENROUTER_API_KEY
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/skv/leetcode-auto",
            "X-Title": "LeetCode Auto Solver"
        }

    if not key:
        print(f"  [JUDGE] API Key is missing, using first result")
        return results[0]['code'] if results else ""

    payload = {
        "model": JUDGE_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 2048,
        "stream": False,
    }

    try:
        timeout = aiohttp.ClientTimeout(total=50)  # 50s for judge phase
        async with session.post(url, headers=headers, json=payload, timeout=timeout) as response:
            if response.status == 200:
                result = await response.json()
                final_output = result['choices'][0]['message']['content']
                return strip_markdown(final_output, language)
            else:
                print(f"  [JUDGE] HTTP {response.status}, falling back to longest result")
                for r in results:
                    if len(r['code'].splitlines()) > 5:
                        return r['code']
                return results[0]['code']
    except Exception as e:
        print(f"  [JUDGE] Error: {e}, using first result")
        return results[0]['code']
