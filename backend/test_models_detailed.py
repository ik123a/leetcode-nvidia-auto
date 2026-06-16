import asyncio
import aiohttp
import os
import sys
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv()

async def test():
    from solvers import MODELS, NVIDIA_URL
    nkey = os.getenv('NVIDIA_API_KEY')
    
    candidates = [
        ("DeepSeek V3.2", MODELS[0]),
        ("Qwen 3 Coder 480B", MODELS[1]),
        ("Llama 3.1 Nemotron 253B", MODELS[2]),
        ("Qwen 3.5 397B", MODELS[3]),
        ("Qwen 2.5 Coder 32B", MODELS[4]),
        ("Llama 3.3 70B Judge", "meta/llama-3.3-70b-instruct")
    ]
    
    print("Querying NVIDIA NIM API models...")
    print("=" * 60)
    async with aiohttp.ClientSession() as session:
        for name, model in candidates:
            headers = {'Authorization': f'Bearer {nkey}', 'Content-Type': 'application/json'}
            payload = {'model': model, 'messages': [{'role': 'user', 'content': 'hi'}], 'max_tokens': 5, 'stream': False}
            try:
                async with session.post(NVIDIA_URL, headers=headers, json=payload, timeout=20) as r:
                    print(f"[{name}] model='{model}' -> HTTP Status: {r.status}")
                    if r.status != 200:
                        body = await r.text()
                        print(f"    Error: {body[:150]}")
            except Exception as e:
                print(f"[{name}] model='{model}' -> ERROR: {e}")
    print("=" * 60)

asyncio.run(test())
