import json
import os
import time
from openai import OpenAI

MODEL_STUDIO_API_KEY = "sk-750246c7b3f347d5aebfe6ced9cd4a6f"  # thay bằng key thật của bạn
MODEL_STUDIO_API_BASE = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
MODEL_NAME = "qwen3.5-plus"  # hoặc "qwen3.5-plus" nếu tên đúng

FEW_SHOT_PATH = "few_shot.json"
TEST_PATH = "test_split.json"
OUTPUT_PATH = "result_qwen.json"

# ── Load few-shot examples ──────────────────────────────────────────────────
few_shot_examples = []
with open(FEW_SHOT_PATH, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            few_shot_examples.append(json.loads(line))

# ── Load test records ───────────────────────────────────────────────────────
test_records = []
with open(TEST_PATH, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            test_records.append(json.loads(line))

# ── Load already-processed IDs (to resume) ─────────────────────────────────
done_ids = set()
if os.path.exists(OUTPUT_PATH):
    with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    obj = json.loads(line)
                    done_ids.add(obj["id"])
                except Exception:
                    pass

print(f"Already done: {len(done_ids)} / {len(test_records)}")

# ── Index few-shot examples by complexity ──────────────────────────────────
few_shot_by_complexity = {}
for ex in few_shot_examples:
    few_shot_by_complexity.setdefault(ex["sql_complexity"], []).append(ex)

def build_few_shot_text(examples):
    blocks = []
    for ex in examples:
        blocks.append(
            f"[Complexity: {ex['sql_complexity']} — {ex['sql_complexity_description']}]\n"
            f"[Task type: {ex['sql_task_type']} — {ex['sql_task_type_description']}]\n"
            f"Context: {ex['sql_context']}\n"
            f"Question: {ex['sql_prompt']}\n"
            f"SQL: {ex['sql']}\n"
            f"Explanation: {ex['sql_explanation']}"
        )
    return "\n\n".join(blocks)

SYSTEM_PROMPT = """You are an expert SQL writer. Given a SQL schema (CREATE TABLE / INSERT statements) and a question in English, write the correct SQL query.

Rules:
- Return ONLY the SQL query, nothing else — no explanation, no markdown, no code fences.
- The SQL must be valid and directly answer the question.
- Use the exact table and column names from the schema.
- Handle all complexity types: basic SQL, aggregation, single join, multiple_joins, subqueries, CTEs, window functions, set operations, DML (INSERT/UPDATE/DELETE).
"""

# ── OpenAI-compatible client ────────────────────────────────────────────────
client = OpenAI(
    api_key=MODEL_STUDIO_API_KEY,
    base_url=MODEL_STUDIO_API_BASE,
)

def generate_sql(record):
    complexity = record["sql_complexity"]
    # Only pass few-shot examples matching the same complexity type
    matched = few_shot_by_complexity.get(complexity, few_shot_examples[:2])
    few_shot_text = build_few_shot_text(matched)

    user_message = (
        f"Here are examples for this complexity type:\n\n{few_shot_text}\n\n"
        f"---\n"
        f"Now write the SQL for:\n"
        f"[Complexity: {record['sql_complexity']} — {record['sql_complexity_description']}]\n"
        f"[Task type: {record['sql_task_type']} — {record['sql_task_type_description']}]\n"
        f"Context: {record['sql_context']}\n"
        f"Question: {record['sql_prompt']}"
    )
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0,
    )
    sql = response.choices[0].message.content.strip()
    # Strip accidental markdown fences
    if sql.startswith("```"):
        sql = sql.split("```")[1]
        if sql.lower().startswith("sql"):
            sql = sql[3:]
        sql = sql.strip()
    return sql

# ── Main loop ───────────────────────────────────────────────────────────────
with open(OUTPUT_PATH, "a", encoding="utf-8") as out_f:
    for i, record in enumerate(test_records):
        rec_id = record["id"]
        if rec_id in done_ids:
            continue

        for attempt in range(3):
            try:
                sql = generate_sql(record)
                line = json.dumps({"id": rec_id, "answer": sql}, ensure_ascii=False)
                out_f.write(line + "\n")
                out_f.flush()
                done_ids.add(rec_id)
                print(f"[{i+1}/{len(test_records)}] id={rec_id} ✓")
                break
            except Exception as e:
                print(f"[{i+1}/{len(test_records)}] id={rec_id} attempt {attempt+1} error: {e}")
                if attempt < 2:
                    time.sleep(5)
                else:
                    print(f"  → Skipping id={rec_id} after 3 failures")

print(f"\nDone! Results written to {OUTPUT_PATH}")
