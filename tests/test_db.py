"""只读查询层的行为约束。

这些是最该被测试盯住的性质：能不能写、会不会把整表拉走、错误分得对不对。
全部不依赖大模型，跑一次几秒。
"""

from __future__ import annotations

import pytest

from data_agent.config import settings
from data_agent.db import ErrorKind, QueryError, _classify, describe_schema, run_query

pytestmark = pytest.mark.skipif(
    not settings.db_path.exists(),
    reason="演示库不存在，先运行 python scripts/build_db.py",
)


def test_select_returns_rows():
    result = run_query("SELECT status, COUNT(*) AS n FROM orders GROUP BY status")
    assert result.columns == ["status", "n"]
    assert result.row_count == 4
    assert not result.truncated


def test_write_is_rejected():
    with pytest.raises(QueryError) as exc:
        run_query("DELETE FROM orders")
    assert exc.value.kind is ErrorKind.SQL
    assert "只允许" in str(exc.value)


def test_limit_is_injected_and_flagged():
    result = run_query("SELECT * FROM order_items")
    assert result.row_count == settings.sql_max_rows
    assert result.truncated, "超过上限时必须标记，否则模型会误以为结果就这么多"


def test_bad_table_is_sql_error():
    with pytest.raises(QueryError) as exc:
        run_query("SELECT * FROM no_such_table")
    assert exc.value.kind is ErrorKind.SQL


def test_classify_maps_transient_and_fatal():
    """偶发问题要能重试，环境故障必须中止——分错了策略就是错的。"""

    class FakeError(Exception):
        pass

    def kind_of(text: str) -> ErrorKind:
        err = FakeError(text)
        return _classify(err)  # type: ignore[arg-type]

    assert kind_of("interrupted") is ErrorKind.TRANSIENT
    assert kind_of("unable to open database file") is ErrorKind.TRANSIENT
    assert kind_of("database is locked") is ErrorKind.TRANSIENT
    assert kind_of("disk I/O error") is ErrorKind.FATAL
    assert kind_of("no such column: foo") is ErrorKind.SQL


def test_schema_carries_metric_definitions():
    text = describe_schema()
    assert "成交额" in text and "不含运费" in text
    assert "不是折扣率" in text, "discount 的语义必须出现在 schema 里，否则模型会当比例用"
