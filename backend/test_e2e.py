import asyncio
import aiohttp
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

async def test_solve():
    """Simulate a real /solve request to the backend."""
    payload = {
        "title": "Two Sum",
        "description": "Given an array of integers nums and an integer target, return indices of the two numbers such that they add up to target. You may assume that each input would have exactly one solution, and you may not use the same element twice.",
        "boilerplate": "class Solution {\npublic:\n    vector<int> twoSum(vector<int>& nums, int target) {\n        \n    }\n};",
        "error_text": None,
        "model_index": None
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post("http://127.0.0.1:5050/solve", json=payload, timeout=aiohttp.ClientTimeout(total=120)) as r:
                data = await r.json()
                if data.get('success'):
                    print(f"[SUCCESS] Got code ({len(data['code'])} chars):")
                    print(data['code'][:500])
                else:
                    print(f"[FAILED] {data.get('error')}")
                    print(f"Rate limited: {data.get('is_rate_limit')}")
        except Exception as e:
            print(f"[ERROR] {e}")
            print("Is the backend running? Start it with: python main.py")

asyncio.run(test_solve())
