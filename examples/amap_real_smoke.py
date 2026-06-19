"""Smoke test: 真实高德 MCP key 跑通.

验证:
1. AmapClient.list_tools() 拿到 12 个 tool
2. geocode 真实解析
3. search_around 真实查 POI
"""
from food_agent.mcp.amap_client import AmapClient

client = AmapClient(use_mock=False)
try:
    # 1. list_tools
    tools = client.list_tools()
    print(f"高德 MCP 实际提供 {len(tools)} 个 tool:")
    for t in tools[:5]:
        print(f"  - {t['name']}: {t.get('description', '')[:50]}")
    if len(tools) > 5:
        print(f"  ... 还有 {len(tools) - 5} 个")

    # 2. geocode
    print("\ngeocode '北京海淀中关村' →")
    result = client.geocode("北京海淀中关村")
    for k, v in result.items():
        print(f"  {k}: {v}")

    # 3. search_around
    if result.get("location"):
        lng = result["location"]["lng"]
        lat = result["location"]["lat"]
        print(f"\nsearch_around ({lng}, {lat}) keywords='川菜' radius=2000 →")
        pois = client.search_around(lng, lat, "川菜", radius=2000)
        for p in pois[:3]:
            print(f"  - {p.get('name')}: {p.get('address')} (距 {p.get('distance')}m)")
    else:
        print("  geocode 没返回 location, 跳过 search_around")
finally:
    client.close()

print("\nOK")