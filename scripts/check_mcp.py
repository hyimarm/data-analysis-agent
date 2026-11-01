"""MCP 自检：客户端拉起服务、列出工具、调用一次。"""

import asyncio
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_mcp_adapters.client import MultiServerMCPClient


async def main() -> None:
    client = MultiServerMCPClient(
        {
            "data": {
                "transport": "stdio",
                "command": sys.executable,
                "args": ["-m", "mcp_server.server"],
                "cwd": str(ROOT),  # ← 关键：显式指定子进程的工作目录
            }
        }
    )

    tools = await client.get_tools()
    print("拿到的工具：", [t.name for t in tools])

    by_name = {t.name: t for t in tools}

    print("\n--- 调 schema ---")
    print(str(await by_name["schema"].ainvoke({}))[:300])

    print("\n--- 调 query ---")
    sql = "SELECT level, COUNT(*) AS n FROM customers GROUP BY level ORDER BY n DESC"
    print(await by_name["query"].ainvoke({"sql": sql}))

    print("\n--- 调 query（故意写错表名）---")
    print(await by_name["query"].ainvoke({"sql": "SELECT * FROM no_such_table"}))


if __name__ == "__main__":
    asyncio.run(main())