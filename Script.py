import json

file_path = "dataset/test.json"  # file của bạn (mỗi dòng là 1 JSON)

sql_complexities = set()

with open(file_path, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            complexity = data.get("sql_complexity")
            if complexity:
                sql_complexities.add(complexity)
        except json.JSONDecodeError:
            print("Lỗi parse JSON:", line)

# In kết quả
print("Các sql_complexity khác nhau:")
for c in sorted(sql_complexities):
    print("-", c)