#!/usr/bin/env python3
"""快速测试 review_summary 是否返回"""

import requests

resp = requests.post(
    "http://127.0.0.1:8765/api/chat",
    json={
        "message": "今天过得有点乱，帮我复盘一下今天发生了什么。",
        "memory_enabled": True,
        "use_v2_brain": True,
    },
    timeout=60
)

data = resp.json()
print("reply:", data.get("reply", "")[:100])
print("review_summary:", data.get("review_summary"))
print("structured:", data.get("review_summary", {}).get("structured") if data.get("review_summary") else None)
