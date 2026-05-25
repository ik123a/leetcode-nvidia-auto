import os
import aiohttp
import asyncio
import re
from dotenv import load_dotenv

load_dotenv()

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

# ============ UPDATED MODELS (APRIL 12 2026) ============
# Optimized for SUPREME CODING ACCURACY. Best models first.
MODELS = [
    "deepseek-ai/deepseek-v3.2",                  # State-of-the-art reasoning (top pick)
    "qwen/qwen3-coder-480b-a35b-instruct",        # Purpose-built coder (480B MoE)
    "nvidia/llama-3.1-nemotron-ultra-253b-v1",     # Highest accuracy Nemotron (253B)
    "qwen/qwen3.5-397b-a17b",                     # Massive reasoning MoE (397B)
    "qwen/qwen2.5-coder-32b-instruct",            # Fast coding expert (32B)
]


def get_language_name(lang_id):
    mapping = {
        "cpp": "C++",
        "python": "Python3",
        "python3": "Python3",
        "javascript": "JavaScript",
        "typescript": "TypeScript",
        "java": "Java",
        "csharp": "C#",
        "go": "Go",
        "rust": "Rust",
        "kotlin": "Kotlin",
        "swift": "Swift",
        "scala": "Scala",
        "php": "PHP",
        "ruby": "Ruby"
    }
    return mapping.get(lang_id.lower(), lang_id)


def strip_markdown(text, language="cpp"):
    """Robustly extract the solution code from AI markdown output based on language."""
    if not text or not isinstance(text, str):
        return ""
    
    lang_name = get_language_name(language).lower()
    
    # Try language-specific blocks first
    code_blocks = re.findall(rf'```(?:{language}|{lang_name})?\s*(.*?)```', text, re.DOTALL | re.IGNORECASE)
    if not code_blocks:
        # Fallback to any markdown block
        code_blocks = re.findall(r'```(?:\w+)?\s*(.*?)```', text, re.DOTALL)
        
    if code_blocks:
        for block in code_blocks:
            if "class Solution" in block or "def " in block or "function " in block:
                return block.strip()
        return code_blocks[0].strip()
    
    # Regex structure fallback for OOP languages
    if language.lower() in ["cpp", "java", "csharp"]:
        match = re.search(r'(class\s+Solution\s*\{.*?\};?)', text, re.DOTALL)
        if match:
            return match.group(1).strip()
    elif language.lower() in ["python", "python3"]:
        match = re.search(r'(class\s+Solution\s*:.*)', text, re.DOTALL)
        if match:
            return match.group(1).strip()
            
    code = text.replace(f"```{language}", "").replace("```", "")
    return code.strip()


async def call_model(session, model_name, problem_data, is_fix=False):
    # --- NVIDIA NIM ONLY ---
    url = NVIDIA_URL
    key = NVIDIA_API_KEY
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }
    
    if not key:
        print(f"  [SKIP] NVIDIA API Key is missing in .env")
        return {"model": model_name, "error": "NVIDIA Key Missing", "success": False}

    language = problem_data.get('language', 'cpp')
    lang_name = get_language_name(language)

    # CRITICAL: Prevent redefinition of common LC structures per language (Safely handle None)
    bp = problem_data.get('boilerplate') or ""
    PROMPT_GUARD = ""
    if lang_name.lower() in ["c++", "cpp", "java", "c#", "csharp"]:
        if "ListNode" in bp or "TreeNode" in bp:
            PROMPT_GUARD = f"\nCRITICAL: Do NOT redefine 'struct ListNode', 'struct TreeNode', or other types already defined in the problem header. LeetCode handles these globally.\n"
    elif lang_name.lower() in ["python", "python3"]:
        if "ListNode" in bp or "TreeNode" in bp:
            PROMPT_GUARD = f"\nCRITICAL: Do NOT redefine classes 'ListNode' or 'TreeNode'. LeetCode imports these globally.\n"

    if is_fix:
        error_type = "Logic Error (Wrong Answer)" if problem_data.get('is_logic_error') else "Compilation/Runtime Error"
        prompt = f"""Fix this {lang_name} solution for '{problem_data['title']}' ({error_type}).{PROMPT_GUARD}

PROBLEM: {problem_data['description']}

BROKEN CODE:
{problem_data['boilerplate']}

ERROR: {problem_data['error_text']}
"""
        if problem_data.get('is_logic_error'):
            prompt += f"""
FAILING TEST: Input={problem_data.get('input_data','N/A')}, Got={problem_data.get('actual_output','N/A')}, Expected={problem_data.get('expected_output','N/A')}
"""
        prompt += f"""
Return ONLY the complete fixed {lang_name} Solution class/function. Full logic, no empty bodies. Include standard libraries if needed. No explanations."""
    else:
        prompt = f"""Solve this LeetCode problem in {lang_name}.{PROMPT_GUARD}

Problem: {problem_data['title']}
Description: {problem_data['description']}

Template:
{problem_data['boilerplate']}

Return ONLY the complete {lang_name} Solution structure with full implementation. No explanations. Optimize for time+space."""

    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 2048,
        "top_p": 0.9,
        "stream": False,
    }

    MAX_RETRIES = 2
    for attempt in range(MAX_RETRIES + 1):
        try:
            timeout = aiohttp.ClientTimeout(total=45) 
            async with session.post(url, headers=headers, json=payload, timeout=timeout) as response:
                if response.status == 200:
                    result = await response.json()
                    message = result.get('choices', [{}])[0].get('message', {})
                    raw_output = message.get('content')
                    
                    if not raw_output:
                        raw_output = message.get('reasoning')
                    
                    if not raw_output:
                        print(f"  [FAIL] {model_name} returned null/empty content and reasoning")
                        return {"model": model_name, "error": "Null AI response", "success": False}
                    
                    clean_code = strip_markdown(raw_output, language)
                    
                    # Language-agnostic code verification (not requiring { } which Python lacks)
                    if len(clean_code.splitlines()) >= 2 and (len(clean_code) > 25 or "class " in clean_code or "def " in clean_code):
                        print(f"  [OK] {model_name} returned valid code ({len(clean_code)} chars) for {lang_name}")
                        return {"model": model_name, "code": clean_code, "success": True}
                    else:
                        return {"model": model_name, "error": "Empty/incomplete solution", "success": False}
                elif response.status == 404 and attempt < MAX_RETRIES:
                    error_body = await response.text()
                    print(f"  [RETRY] {model_name} got 404 (attempt {attempt+1}/{MAX_RETRIES+1}), retrying in 3s...")
                    await asyncio.sleep(3)
                    continue
                else:
                    error_body = await response.text()
                    print(f"  [FAIL] {model_name} HTTP {response.status}: {error_body[:200]}")
                    return {"model": model_name, "error": f"Status {response.status}: {error_body[:100]}", "success": False}
        except asyncio.TimeoutError:
            print(f"  [TIMEOUT] {model_name} timed out after 45s")
            return {"model": model_name, "error": "Timeout (45s)", "success": False}
        except Exception as e:
            error_msg = str(e)[:100]
            print(f"  [ERR] {model_name} exception: {error_msg}")
            return {"model": model_name, "error": error_msg, "success": False}
    
    return {"model": model_name, "error": "All retries exhausted (404)", "success": False}


async def call_model_with_history(session, model_name, problem_data, previous_attempts):
    """
    Enhanced solver that feeds ALL previous failed attempts into the prompt,
    so each subsequent model 'evolves' and avoids past mistakes.
    """
    url = NVIDIA_URL
    key = NVIDIA_API_KEY
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }

    if not key:
        print(f"  [SKIP] NVIDIA API Key is missing in .env")
        return {"model": model_name, "error": "NVIDIA Key Missing", "success": False}

    language = problem_data.get('language', 'cpp')
    lang_name = get_language_name(language)

    bp = problem_data.get('boilerplate') or ""
    PROMPT_GUARD = ""
    if lang_name.lower() in ["c++", "cpp", "java", "c#", "csharp"]:
        if "ListNode" in bp or "TreeNode" in bp:
            PROMPT_GUARD = f"\nCRITICAL: Do NOT redefine 'struct ListNode', 'struct TreeNode', or other types already defined in the problem header. LeetCode handles these globally.\n"
    elif lang_name.lower() in ["python", "python3"]:
        if "ListNode" in bp or "TreeNode" in bp:
            PROMPT_GUARD = f"\nCRITICAL: Do NOT redefine classes 'ListNode' or 'TreeNode'. LeetCode imports these globally.\n"

    # Build the evolution context from previous attempts
    history_context = ""
    if previous_attempts:
        history_context = f"\n\n=== PREVIOUS FAILED ATTEMPTS IN {lang_name.upper()} (LEARN FROM THESE MISTAKES) ===\n"
        for i, attempt in enumerate(previous_attempts):
            history_context += f"\n--- Attempt {i+1} by {attempt.get('model', 'unknown')} ---\n"
            history_context += f"Code:\n{attempt.get('code', 'N/A')}\n"
            history_context += f"Result: {attempt.get('result', 'unknown')}\n"
            if attempt.get('error_text'):
                history_context += f"Error Details: {attempt['error_text']}\n"
            if attempt.get('input_data'):
                history_context += f"Failing Input: {attempt['input_data']}\n"
            if attempt.get('expected_output'):
                history_context += f"Expected Output: {attempt['expected_output']}\n"
            if attempt.get('actual_output'):
                history_context += f"Actual Output: {attempt['actual_output']}\n"
        history_context += "\n=== END OF PREVIOUS ATTEMPTS ===\n"
        history_context += f"\nYou MUST produce a DIFFERENT and BETTER {lang_name} solution. Analyze why each previous attempt failed and avoid the same mistakes.\n"

    prompt = f"""Solve this LeetCode problem in {lang_name}.{PROMPT_GUARD}

Problem: {problem_data['title']}
Description: {problem_data['description']}

Template:
{problem_data['boilerplate']}
{history_context}
Return ONLY the complete {lang_name} Solution class/structure with full implementation. No explanations. Optimize for correctness first, then time+space."""

    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3 + (0.1 * len(previous_attempts)),  # Increase creativity with more failures
        "max_tokens": 3072,  # More tokens for harder problems
        "top_p": 0.9,
        "stream": False,
    }

    MAX_RETRIES = 2
    for attempt in range(MAX_RETRIES + 1):
        try:
            timeout = aiohttp.ClientTimeout(total=60)  # More time for complex problems
            async with session.post(url, headers=headers, json=payload, timeout=timeout) as response:
                if response.status == 200:
                    result = await response.json()
                    message = result.get('choices', [{}])[0].get('message', {})
                    raw_output = message.get('content')

                    if not raw_output:
                        raw_output = message.get('reasoning')

                    if not raw_output:
                        print(f"  [FAIL] {model_name} returned null/empty content")
                        return {"model": model_name, "error": "Null AI response", "success": False}

                    clean_code = strip_markdown(raw_output, language)

                    # Language-agnostic validation
                    if len(clean_code.splitlines()) >= 2 and (len(clean_code) > 25 or "class " in clean_code or "def " in clean_code):
                        print(f"  [OK] {model_name} returned valid code ({len(clean_code)} chars, attempt context: {len(previous_attempts)} prior failures) for {lang_name}")
                        return {"model": model_name, "code": clean_code, "success": True}
                    else:
                        return {"model": model_name, "error": "Empty/incomplete solution", "success": False}
                elif response.status == 404 and attempt < MAX_RETRIES:
                    print(f"  [RETRY] {model_name} got 404 (attempt {attempt+1}), retrying in 3s...")
                    await asyncio.sleep(3)
                    continue
                else:
                    error_body = await response.text()
                    print(f"  [FAIL] {model_name} HTTP {response.status}: {error_body[:200]}")
                    return {"model": model_name, "error": f"Status {response.status}: {error_body[:100]}", "success": False}
        except asyncio.TimeoutError:
            print(f"  [TIMEOUT] {model_name} timed out after 60s")
            return {"model": model_name, "error": "Timeout (60s)", "success": False}
        except Exception as e:
            error_msg = str(e)[:100]
            print(f"  [ERR] {model_name} exception: {error_msg}")
            return {"model": model_name, "error": error_msg, "success": False}

    return {"model": model_name, "error": "All retries exhausted (404)", "success": False}
