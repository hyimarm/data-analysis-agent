import sys
from pathlib import Path
from data_agent.chart import render
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.fastmcp import FastMCP

from data_agent.db import ErrorKind, QueryError, describe_schema, run_query

from data_agent.db import QueryError, describe_schema, run_query
from data_agent.export import export_markdown

mcp = FastMCP("data-analysis-tools")

@mcp.tool()
def query(sql:str) -> str:
    """执行一条只读 SQL 查询，返回表格文本。

        数据库是只读的：只允许 SELECT / WITH / PRAGMA。
        结果最多返回 200 行，超出会标注"已截断"。
        执行失败时返回错误原文，你可以据此修正 SQL 后重试。

        Args:
            sql: 标准 SQLite 查询语句，不要带分号也可以。
    """
    try:
        result = run_query(sql)
    except QueryError as exc:
        if exc.kind is ErrorKind.SQL:
            return (
                f"[SQL_ERROR] {exc}\n"
                "改 SQL 可解：检查表名、列名、聚合语法，修正后重试。"
            )
        if exc.kind is ErrorKind.TRANSIENT:
            return (
                f"[TRANSIENT_ERROR] {exc}\n"
                "这是偶发问题（超时或资源竞争）。可以重试一次，"
                "但请先把查询简化：加 WHERE 缩小范围、先聚合再 join、减少嵌套。"
            )
        return (
            f"[FATAL_ERROR] {exc}\n"
            "数据库环境故障，改 SQL 无法解决。立即停止，把错误告知用户。"
        )
    except Exception as exc:
        return f"[ENV_ERROR] 未知错误：{exc}\n这不是 SQL 问题，不要重试。"

    text = result.to_text()
    if result.truncated:
        text += f"\n（已截断：实际结果超过 {result.row_count} 行，建议加 WHERE 或聚合）"
    return text

@mcp.tool()
def schema() -> str:
    """查看数据库的表结构：表名、字段、类型、行数。

    不确定该查哪张表时，先调用这个。
    """
    return describe_schema()

@mcp.tool()
def chart(
    sql: str,
    kind: str = "bar",
    x: str = "",
    y: str = "",
    title: str = "",
    y_label: str = "",
) -> str:
    """把一条查询的结果画成图片，返回 PNG 文件路径。

    先想清楚用哪种图，再写 SQL：
    - 时间趋势 → kind="line"（x 传月份字段，y 传数值字段）
    - 类别对比 → kind="bar"
    - 占比构成 → kind="pie"（只放 5 个以内的类别，太多会看不清）
    - 相关性   → kind="scatter"

    SQL 应只返回两列：一列类别/时间（x），一列数值（y）。
    数值列请提前用 ROUND 保留两位小数。

    Args:
        sql: 用于取数的只读 SQL，建议已按 x 排序。
        kind: bar / line / pie / scatter
        x: 作为横轴的列名；留空则取第一列。
        y: 作为纵轴的列名；留空则取第二列。
        title: 图表标题，用中文描述这张图说明什么。
        y_label: 纵轴的中文含义，例如"成交额""订单数"；留空则用列名。
    """

    try:
        path = render(sql, kind=kind, x=x, y=y, title=title, y_label=y_label)
        return f"图表已生成：{path}"
    except QueryError as exc:
        return f"[SQL_ERROR] {exc}"
    except Exception as exc:
        return f"[FATAL_ERROR] 绘图失败：{exc}"

@mcp.tool()
def export_report(title: str, content: str) -> str:
    """把一段 Markdown 内容保存成报告文件，返回文件路径。

    用户说"导出""保存成报告""给我一份文档"时调用。
    content 用 Markdown 写：标题、表格、结论都可以；
    引用的图片写成 ![说明](图片文件名)，例如 ![成交额趋势](chart_e88ce4d7.png)。

    Args:
        title: 报告标题，会用作文件名，不要带特殊符号。
        content: 完整的 Markdown 正文。
    """
    try:
        path = export_markdown(title, content)
        return f"报告已保存：{path}"
    except Exception as exc:
        return f"[FATAL_ERROR] 导出失败：{exc}"

if __name__ == "__main__":
    # 默认 stdio 传输：客户端启动本进程，通过 stdin/stdout 收发消息
    mcp.run()