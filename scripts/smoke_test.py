import requests, json
body = {
  "area": 60.0, "layout": "2室1厅1卫", "grade": "简装", "pack": "全包",
  "style": "简约", "special": [], "district": "瑶海区", "contact": "13800138001"
}
r = requests.post("http://127.0.0.1:8000/api/quote?force_fallback=true", json=body, timeout=10)
print("Status:", r.status_code)
data = r.json()
print("Total:", data.get("total"))
print("Source:", data.get("source"))
print("Items count:", len(data.get("items", [])))
print("Breakdown:", data.get("breakdown"))
print("First 3 items:")
for it in data.get("items", [])[:3]:
    print(f"  - {it['name']}: {it['quantity']} x {it['unit_price']} = {it['total']}")
