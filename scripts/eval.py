"""跑评测集：比对最终数字，而不只看 SQL 能不能执行。"""

import asyncio
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data_agent.agent import build_agent
from data_agent.db import run_query

TOL = 0.001  # 相对误差 0.1%，比"心算错 0.02 个百分点"更严
ABS_FLOOR = 0.05   # 绝对误差下限：小于 100 的量（百分比、比率）用它


def expected(sql: str) -> float:
    return float(run_query(sql).rows[0][0])


def numbers(text: str) -> list[float]:
    found = re.findall(r"-?\d[\d,]*\.?\d*", str(text))
    return [float(x.replace(",", "")) for x in found]


def is_hit(answer: str, exp: float) -> bool:
    head = str(answer)[:400]
    nums = numbers(head)
    limit = max(abs(exp) * TOL, ABS_FLOOR)
    if exp == 0:
        return any(abs(n) < 1e-6 for n in nums)
    return any(abs(n - exp) <= limit for n in nums)


async def main() -> None:
    path = ROOT / "eval" / "questions.jsonl"
    questions = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    value_qs = [q for q in questions if q.get("type", "value") == "value"]
    open_qs = [q for q in questions if q.get("type") == "open"]

    agent = await build_agent()
    hit_count = 0

    print("=== 自动判分 ===")
    for q in value_qs:
        exp = expected(q["sql"])
        result = await agent.ainvoke({"messages": [{"role": "user", "content": q["question"]}]})
        msgs = result["messages"]
        answer = ""
        for m in reversed(msgs):
            if getattr(m, "content", None) and not getattr(m, "tool_calls", None):
                answer = str(m.content)
                break
        calls = sum(1 for m in msgs if getattr(m, "tool_calls", None))
        env_err = any("[ENV_ERROR]" in str(m.content) for m in msgs)
        ok = (not env_err) and is_hit(answer, exp)
        hit_count += ok
        print(f"{'✅' if ok else '❌'} {q['id']:20s} 期望={exp:<14} 调用={calls}")
        if not ok:
            print(f"   答案: {answer[:100].replace(chr(10), ' ')}")

    print("\n=== 人工判读（不计分）===")
    for q in open_qs:
        result = await agent.ainvoke({"messages": [{"role": "user", "content": q["question"]}]})
        msgs = result["messages"]
        answer = ""
        for m in reversed(msgs):
            if getattr(m, "content", None) and not getattr(m, "tool_calls", None):
                answer = str(m.content)
                break
        calls = sum(1 for m in msgs if getattr(m, "tool_calls", None))
        print(f"· {q['id']:20s} 调用={calls}  {answer[:150].replace(chr(10), ' ')}")

    total = len(value_qs)
    print(f"\n自动判分准确率 {hit_count}/{total} = {hit_count / total:.1%}")




if __name__ == "__main__":
    asyncio.run(main())