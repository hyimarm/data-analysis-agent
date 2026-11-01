"""数据库自检：结构 + 正常查询 + 写操作拦截。"""

import sys
from pathlib import Path

# 让脚本能 import 到项目里的包（不依赖 PyCharm 的 PYTHONPATH 设置）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data_agent.db import describe_schema, run_query, QueryError


def main() -> None:
    print(describe_schema()[:600])

    print("\n--- 正常查询 ---")
    result = run_query("SELECT status, COUNT(*) AS n FROM orders GROUP BY status")
    print(result.to_text())
    print(f"（{result.elapsed_ms:.1f} ms）")

    print("\n--- 尝试写操作（应该被拒绝）---")
    try:
        run_query("DELETE FROM orders")
    except QueryError as exc:
        print("已拦截：", exc)

    print("\n--- 尝试无 LIMIT 的大查询（应被截断）---")
    big = run_query("SELECT * FROM order_items")
    print(f"返回 {big.row_count} 行，truncated = {big.truncated}")


if __name__ == "__main__":
    main()