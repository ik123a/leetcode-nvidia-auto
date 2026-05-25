from flask import Flask, request, jsonify
from flask_cors import CORS
import asyncio
import aiohttp
import sys
import os

# Fix Windows console encoding for emoji/unicode in logs
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from solvers import call_model, call_model_with_history, MODELS
from judge import judge_solutions
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)


def run_async(coro):
    """Run async code from sync Flask routes without needing flask[async]."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _solve(problem_data, is_fix, model_index=None):
    async with aiohttp.ClientSession() as session:
        # Sequential Rotation Strategy
        if model_index is not None and 0 <= model_index < len(MODELS):
            target_models = [MODELS[model_index]]
        else:
            # Parallel Race Strategy (Default)
            target_models = MODELS

        tasks = [call_model(session, m, problem_data, is_fix=is_fix) for m in target_models]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    # Filter successful results
    valid_results = []
    for r in results:
        if isinstance(r, dict) and r.get('success'):
            valid_results.append(r)

    if not valid_results:
        return None, results

    # If only 1 valid result, use it directly (skip judge)
    if len(valid_results) == 1:
        return valid_results[0]['code'], results

    # Multiple results — let the judge pick
    async with aiohttp.ClientSession() as session:
        final_code = await judge_solutions(session, problem_data, valid_results)
    return final_code, results


async def _solve_evolve(problem_data, model_name, previous_attempts):
    """Single-model call with full history context for evolution-based solving."""
    async with aiohttp.ClientSession() as session:
        result = await call_model_with_history(session, model_name, problem_data, previous_attempts)
    return result


@app.route('/solve', methods=['POST'])
def solve():
    data = request.json
    title = data.get('title')
    description = data.get('description')
    boilerplate = data.get('boilerplate')
    error_text = data.get('error_text')
    language = data.get('language', 'cpp')

    if not title or not description:
        return jsonify({"success": False, "error": "Missing data"})

    problem_data = {
        "title": title,
        "description": description,
        "boilerplate": boilerplate,
        "language": language,
        "error_text": error_text,
        "is_logic_error": data.get('is_logic_error'),
        "input_data": data.get('input_data'),
        "actual_output": data.get('actual_output'),
        "expected_output": data.get('expected_output')
    }

    is_fix = bool(error_text)
    model_index = data.get('model_index')
    try:
        final_code, results = run_async(_solve(problem_data, is_fix, model_index))
    except Exception as e:
        import traceback
        print(f"[BACKEND ERROR]\n{traceback.format_exc()}")
        return jsonify({"success": False, "error": f"Internal Error: {str(e)}", "is_rate_limit": False})

    if final_code:
        return jsonify({"success": True, "code": final_code})
    else:
        is_rate_limited = any("429" in str(r.get('error','')) for r in results if isinstance(r, dict))
        all_errors = [r.get('error') for r in results if isinstance(r, dict) and r.get('error')]
        error_msg = all_errors[0] if all_errors else "All AI models failed."
        return jsonify({
            "success": False, 
            "error": "Rate limit exceeded" if is_rate_limited else error_msg,
            "is_rate_limit": is_rate_limited
        })


@app.route('/solve_evolve', methods=['POST'])
def solve_evolve():
    """Evolution endpoint: single model call with full history of previous failures."""
    data = request.json
    title = data.get('title')
    description = data.get('description')
    boilerplate = data.get('boilerplate')
    model_name = data.get('model_name')
    previous_attempts = data.get('previous_attempts', [])
    language = data.get('language', 'cpp')

    if not title or not description or not model_name:
        return jsonify({"success": False, "error": "Missing data (title/description/model_name)"})

    problem_data = {
        "title": title,
        "description": description,
        "boilerplate": boilerplate,
        "language": language,
    }

    try:
        result = run_async(_solve_evolve(problem_data, model_name, previous_attempts))
    except Exception as e:
        import traceback
        print(f"[BACKEND ERROR]\n{traceback.format_exc()}")
        return jsonify({"success": False, "error": f"Internal Error: {str(e)}"})

    if result.get('success'):
        return jsonify({"success": True, "code": result['code'], "model": result['model']})
    else:
        return jsonify({"success": False, "error": result.get('error', 'Unknown error'), "model": result.get('model')})


@app.route('/models', methods=['GET'])
def get_models():
    """Return list of available models for the bot to iterate through."""
    return jsonify({"models": MODELS})


@app.route('/health', methods=['GET'])
def health():
    or_key = os.getenv("OPENROUTER_API_KEY")
    nv_key = os.getenv("NVIDIA_API_KEY")
    return jsonify({
        "status": "healthy",
        "openrouter_key_set": bool(or_key and len(or_key) > 20),
        "nvidia_key_set": bool(nv_key and nv_key.startswith("nvapi-")),
        "key_set": bool(or_key and nv_key), # Restored for extension compatibility
        "models": MODELS
    })


if __name__ == '__main__':
    app.run(port=5050, debug=True)
