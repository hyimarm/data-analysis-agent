"""把结论文本导出为 Markdown 文件。"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from .config import settings

# 文件名里只保留中文、字母、数字、点、横线，其余一律换成下划线
_SAFE = re.compile(r"[^\w\u4e00-\u9fff.-]+")
_IMG = re.compile(r"!\[([^\]]*)\]\(([^)]+\.(?:png|jpg|jpeg|svg))\)")

def _normalize_images(markdown: str) -> str:
    """报告在 outputs/，图片在 charts/，把裸文件名统一改写成 ../charts/文件名。"""
    return _IMG.sub(
        lambda m: f"![{m.group(1)}](../charts/{Path(m.group(2)).name})",
        markdown,
    )

def export_markdown(title: str, content: str) -> Path:
    settings.output_dir.mkdir(parents=True, exist_ok=True)

    stem = _SAFE.sub("_", title).strip("_")[:40] or "report"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = (settings.output_dir / f"{stem}_{stamp}.md").resolve()

    # 双保险：即使文件名清洗有漏，也不允许写出输出目录
    if settings.output_dir.resolve() not in path.parents:
        raise ValueError(f"非法的输出路径：{path}")

    path.write_text(_normalize_images(content), encoding="utf-8")
    return path

