#!/usr/bin/env python3
"""直接测试后端 API 的双明手分析"""

import urllib.request
import json

# 测试数据 - 注意：后端期望的是 spades/hearts/diamonds/clubs 字段
hands = {
    "hands": {
        "南": {"spades": "8", "hearts": "J98643", "diamonds": "Q7654", "clubs": "6"},
        "西": {"spades": "AK762", "hearts": "KT2", "diamonds": "2", "clubs": "AQ73"},
        "北": {"spades": "QJ94", "hearts": "5", "diamonds": "KT98", "clubs": "T954"},
        "东": {"spades": "T53", "hearts": "AQ7", "diamonds": "AJ3", "clubs": "KJ82"}
    }
}

print("测试后端 API: POST /api/double-dummy")
print("=" * 60)

try:
    data = json.dumps(hands).encode('utf-8')
    req = urllib.request.Request(
        "http://localhost:8003/api/double-dummy",
        data=data,
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    
    with urllib.request.urlopen(req, timeout=30) as response:
        result = json.loads(response.read().decode('utf-8'))
        
        if result.get('success'):
            table_data = result.get('table_data', {})
            print("双明手分析结果:")
            print(f"  东 S: {table_data.get('东', {}).get('S', {})}")
            print(f"  西 S: {table_data.get('西', {}).get('S', {})}")
            
            east_s = table_data.get('东', {}).get('S', {})
            west_s = table_data.get('西', {}).get('S', {})
            
            if east_s.get('max_level') == 5 and west_s.get('max_level') == 5:
                print("\n[OK] 后端返回正确结果: 东西都可以打到 5S")
            else:
                print(f"\n[ERROR] 后端返回错误结果:")
                print(f"  东 S: {east_s.get('contract', 'N/A')}")
                print(f"  西 S: {west_s.get('contract', 'N/A')}")
                print("\n可能原因: 后端未重启或缓存了旧代码")
        else:
            print(f"分析失败: {result.get('error')}")
            
except urllib.error.URLError as e:
    print(f"[ERROR] 无法连接到后端: {e}")
    print("请确认服务已启动: uvicorn api.main:app --host 0.0.0.0 --port 8003")
except Exception as e:
    print(f"[ERROR] {e}")
