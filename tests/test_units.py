"""图表单位换算、报告图片路径修正、评测判分容差。

这三个都是"输出给人看"的环节，出错不影响正确性，但会让结果没法直接用。
"""

from __future__ import annotations

import pytest

from data_agent.chart import _pick_unit
from data_agent.export import _normalize_images


@pytest.mark.parametrize(
    ("values", "scale", "unit"),
    [
        ([44462665.78, 41194233.24], 1e4, "万元"),
        ([1.5e9, 2.0e9], 1e8, "亿元"),
        ([263, 1311, 804], 1.0, ""),
        ([], 1.0, ""),
    ],
)
def test_pick_unit(values, scale, unit):
    got_scale, got_unit = _pick_unit(values)
    assert got_scale == scale
    assert got_unit == unit


@pytest.mark.parametrize(
    "src",
    [
        "![图](chart_abc.png)",
        "![图](charts/chart_abc.png)",
        "![图](./charts/chart_abc.png)",
    ],
)
def test_image_path_normalized(src):
    """报告在 outputs/，图片在 charts/，任何写法的裸路径都要改对。"""
    out = _normalize_images(src)
    assert out == "![图](../charts/chart_abc.png)"


def test_http_image_untouched():
    src = "![图](https://example.com/a.png)"
    assert _normalize_images(src) == src


def test_is_hit_tolerance():
    """容差要跟量级走：大批量允许 0.1%，小数值用绝对下限。"""
    from scripts.eval import is_hit

    assert is_hit("总成交额 44,462,665.78 元", 44462665.78)
    assert is_hit("占比 4.81%", 4.80), "舍入差异不该判错"
    assert not is_hit("总成交额 41,194,233.24 元", 44462665.78)
