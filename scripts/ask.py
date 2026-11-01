"""用mcp工具跑一个数据问答agent"""


import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from langchain.agents import create_agent
from langchain_core.messages import *
from data_agent.agent import build_agent


def print_trace(messages)->None:
    """打印完整轨迹，确定模型没有编造答案"""
    for m in messages:
        if isinstance(m, HumanMessage):
            print(f"\n[用户] {m.content}")
        elif isinstance(m, AIMessage):
            for tc in m.tool_calls:
                print(f"[调用] {tc['name']}({tc['args']})")
            if m.content:
                print(f"[回答] {m.content}")
        elif isinstance(m, ToolMessage):
            preview = str(m.content)[:180].replace("\n", " ")
            print(f"[结果] {preview}")

async def main() -> None:
    question = sys.argv[1] if len(sys.argv) > 1 else "各个会员等级有多少人？"
    agent = await build_agent()
    result = await agent.ainvoke({"messages": [{"role": "user", "content": question}]})
    messages = result["messages"]
    print_trace(messages)

    fatal = [
        str(m.content)
        for m in messages
        if isinstance(m, ToolMessage) and "[FATAL_ERROR]" in str(m.content)
    ]
    if fatal:
        print("\n" + "=" * 60)
        print("数据库环境故障，本次答案作废。")
        print(f"共 {len(fatal)} 次：{fatal[0][:200]}")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
