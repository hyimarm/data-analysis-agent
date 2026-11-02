"""把查询结果画成图。

三个必须处理的问题：
1. 服务端没有显示器，必须用 Agg 后端，否则 import 就崩
2. matplotlib 默认字体不含中文，标题会变成方块
3. 负号会被画成方块（unicode_minus）
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4
from .config import settings

import matplotlib

matplotlib.use("Agg")  # 必须在 import pyplot 之前

import matplotlib.pyplot as plt


from .db import run_query

# Windows 自带雅黑；Linux 服务器一般装 Noto Sans CJK
plt.rcParams["font.sans-serif"] = [
    "Microsoft YaHei",
    "SimHei",
    "Noto Sans CJK SC",
    "WenQuanYi Micro Hei",
]
plt.rcParams["axes.unicode_minus"] = False

KINDS = ("bar", "line", "pie", "scatter")
def _pick_unit(values: list[float]) -> tuple[float, str]:
    """按量级选单位：超过一亿用亿，超过一万用万。"""
    peak = max((abs(v) for v in values), default=0)
    if peak >= 1e8:
        return 1e8, "亿元"
    if peak >= 1e4:
        return 1e4, "万元"
    return 1.0, ""


def render(
    sql: str,
    kind: str = "bar",
    x: str = "",
    y: str = "",
    title: str = "",
    y_label: str = "",
) -> Path:
    """执行 SQL 并保存 PNG，返回文件路径。"""
    result = run_query(sql)
    if not result.rows:
        raise ValueError("查询没有返回数据，无法作图")

    cols = result.columns
    xi = cols.index(x) if x in cols else 0
    yi = cols.index(y) if y in cols else (1 if len(cols) > 1 else 0)

    labels = [str(row[xi]) for row in result.rows]
    values = [float(row[yi] or 0) for row in result.rows]
    scale, unit = _pick_unit(values) if kind != "pie" else (1.0, "")
    if scale != 1.0:
        values = [v / scale for v in values]
    kind = kind if kind in KINDS else "bar"
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=120)

    if kind == "bar":
        ax.bar(labels, values, color="#3b6fd4")
        ax.grid(axis="y", alpha=0.3)
    elif kind == "line":
        ax.plot(labels, values, marker="o", color="#3b6fd4")
        ax.grid(axis="y", alpha=0.3)
    elif kind == "pie":
        ax.pie(values, labels=labels, autopct="%1.1f%%")
    else:
        ax.scatter(range(len(labels)), values, color="#3b6fd4")
        ax.grid(axis="y", alpha=0.3)

    if kind != "pie":
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=30, ha="right")
        label = y_label or y or cols[yi]
        ax.set_ylabel(f"{label}（{unit}）" if unit else label)

    ax.set_title(title or "查询结果")
    fig.tight_layout()

    settings.chart_dir.mkdir(parents=True, exist_ok=True)
    path = settings.chart_dir / f"chart_{uuid4().hex[:8]}.png"
    fig.savefig(path)
    plt.close(fig)
    return path