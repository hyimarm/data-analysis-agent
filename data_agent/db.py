"""只读查询层。

三条安全边界，全部由代码或数据库强制，不依赖提示词：

1. 连接本身就是只读的（SQLite URI mode=ro）——写操作在数据库层被拒绝，
   不是靠字符串过滤。字符串过滤会被注释、大小写、多语句绕过。
2. 强制 LIMIT——防止 SELECT * 把十万行拉进内存。
3. 超时中断——防止笛卡尔积把进程拖死。SQLite 没有 statement_timeout，
   只能靠 progress handler 自己实现。
"""

from __future__ import annotations

import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum

from .config import settings

ALLOWED_PREFIX = ("select", "with", "pragma")


METRIC_DEFINITIONS = """\
指标口径（**必须严格遵守，不得自行选择其它算法**）：
- 成交额 = 已付款订单的 Σ(quantity × unit_price) − 订单折扣【不含运费】
- 销售额 = 已付款订单的 Σ(quantity × unit_price)【不含折扣、不含运费】
- 实收金额 = 成交额 + 运费
- 订单数 = COUNT(DISTINCT 订单 id)
- 客单价 = 成交额 / 订单数
- 退款率 = refunded 订单数 / 全部订单数
- "上个月" = 数据中最新一个完整自然月
注意：以上三个金额指标互不相同，回答时必须明确写出你用的是哪一个。
默认规则：**除非明确说"全部订单"，所有指标只统计 status='paid' 的订单。**
"""

class ErrorKind(str, Enum):
    """错误分级：决定模型该不该重试。"""

    SQL = "sql"              # SQL 写错了，改 SQL 可解
    TRANSIENT = "transient"  # 偶发问题（超时、锁、临时文件），重试或简化可解
    FATAL = "fatal"          # 环境坏了，改什么都没用


class QueryError(Exception):
    """SQL 执行失败。message 会被回灌给模型，所以要说人话。"""

    def __init__(self, message: str, kind: ErrorKind = ErrorKind.SQL) -> None:
        super().__init__(message)
        self.kind = kind


@dataclass
class QueryResult:
    sql: str
    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    truncated: bool = False
    elapsed_ms: float = 0.0

    @property
    def row_count(self) -> int:
        return len(self.rows)

    def to_text(self, max_chars: int = 3000) -> str:
        """转成给模型看的文本。行数多时只给前几行，避免撑爆上下文。"""
        if not self.columns:
            return "（无结果）"
        head = " | ".join(self.columns)
        body = "\n".join(
            " | ".join("" if v is None else str(v) for v in row)
            for row in self.rows[:30]
        )
        text = f"{head}\n{body}"
        if self.row_count > 30:
            text += f"\n...（共 {self.row_count} 行，仅显示前 30 行）"
        return text[:max_chars]


def _connect() -> sqlite3.Connection:
    """以只读模式打开数据库。

    file:...?mode=ro 是 SQLite 的 URI 语法：文件不存在会直接报错，
    任何写操作返回 "attempt to write a readonly database"。
    """
    db: Path = settings.db_path
    if not db.exists():
        raise QueryError(f"数据库不存在：{db}，先运行 scripts/build_db.py")
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)

    # 某些环境下临时文件创建会失败（实测 TMPDIR 被设成相对路径），
    # 表现为 GROUP BY / 大聚合报 "unable to open database file"，
    # 而小查询正常——因为前者要落临时 B 树，后者能在内存里做完。
    # 本项目数据在百 MB 以内，把临时表放内存即可。
    conn.execute(f"PRAGMA temp_store = {settings.sql_temp_store}")
    conn.execute("PRAGMA cache_size = -20000")

    return conn


def _strip_trailing(sql: str) -> str:
    return re.sub(r"[;\s]+$", "", sql.strip())

# 这些是基础设施问题，重试 SQL 没有意义
_ENV_HINTS = (
    "unable to open database file",
    "database is locked",
    "disk i/o error",
    "out of memory",
    "interrupted",
)

# 偶发问题：改写法或重试一次通常能过
_TRANSIENT_HINTS = (
    "interrupted",
    "database is locked",
    "unable to open database file",
)

# 真正的环境故障：磁盘、内存、库文件损坏
_FATAL_HINTS = (
    "disk i/o error",
    "out of memory",
    "database disk image is malformed",
)


def _classify(exc: sqlite3.Error) -> ErrorKind:
    text = str(exc).lower()
    if any(hint in text for hint in _FATAL_HINTS):
        return ErrorKind.FATAL
    if any(hint in text for hint in _TRANSIENT_HINTS):
        return ErrorKind.TRANSIENT
    return ErrorKind.SQL


def run_query(sql: str) -> QueryResult:
    """执行一条只读查询。失败抛 QueryError，message 给模型看。"""
    cleaned = _strip_trailing(sql)
    if not cleaned:
        raise QueryError("SQL 为空", kind=ErrorKind.SQL)

    first_word = cleaned.split(maxsplit=1)[0].lower()
    if first_word not in ALLOWED_PREFIX:
        raise QueryError(
            f"只允许 SELECT / WITH / PRAGMA 查询，收到的是 {first_word.upper()}。"
            "这个数据库是只读的，不能修改数据。",
            kind=ErrorKind.SQL
        )

    # 没写 LIMIT 就补一个，避免把整表拉走
    if not re.search(r"\blimit\b", cleaned, re.I):
        cleaned = f"{cleaned} LIMIT {settings.sql_max_rows + 1}"

    deadline = time.monotonic() + settings.sql_timeout_seconds
    started = time.perf_counter()

    conn = _connect()
    try:
        # 每执行 2000 条虚拟机指令检查一次，超时就中止
        conn.set_progress_handler(
            lambda: 1 if time.monotonic() > deadline else 0, 2000
        )
        cursor = conn.execute(cleaned)
        columns = [d[0] for d in cursor.description or []]
        # 多取一行，用来判断是否被截断
        rows = cursor.fetchmany(settings.sql_max_rows + 1)
    except sqlite3.Error as exc:
        raise QueryError(f"SQL 执行失败：{exc}", kind=_classify(exc)) from exc
    finally:
        conn.close()

    truncated = len(rows) > settings.sql_max_rows
    return QueryResult(
        sql=cleaned,
        columns=columns,
        rows=rows[: settings.sql_max_rows],
        truncated=truncated,
        elapsed_ms=(time.perf_counter() - started) * 1000,
    )

# 只有列名和类型不够——模型会反复猜字段含义，甚至把金额当比例。
# 这里把容易误解的字段直接说明白。
COLUMN_NOTES: dict[tuple[str, str], str] = {
    ("customers", "level"): "会员等级：普通 / 白银 / 黄金 / 钻石",
    ("customers", "region"): "所属大区：华东 / 华北 / 华南 / 西南",
    ("orders", "status"): "paid=已付款（唯一算成交）/ refunded=已退款 / cancelled=已取消 / pending=待付款",
    ("orders", "discount"): "订单级减免【金额，单位元】，不是折扣率",
    ("orders", "freight"): "运费【金额，单位元】，独立于商品金额",
    ("orders", "channel"): "下单渠道：app / web / mini",
    ("order_items", "unit_price"): "下单时的成交单价，可能不等于 products.list_price",
    ("products", "list_price"): "当前标价；历史订单金额请用 order_items.unit_price",
}


def describe_schema() -> str:
    """返回库结构，供模型决定查哪张表。"""
    conn = _connect()
    try:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        ]
        blocks = []
        for table in tables:
            cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
            lines = [f"表 {table}"]
            for _cid, name, ctype, notnull, _default, pk in cols:
                flags = []
                if pk:
                    flags.append("PK")
                if notnull:
                    flags.append("NOT NULL")
                suffix = f"  [{', '.join(flags)}]" if flags else ""
                note = COLUMN_NOTES.get((table, name))
                comment = f"  — {note}" if note else ""
                lines.append(f"  - {name} {ctype}{suffix}{comment}")
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            lines.append(f"  （{count:,} 行）")
            blocks.append("\n".join(lines))
        return METRIC_DEFINITIONS + "\n" + "\n\n".join(blocks)
    finally:
        conn.close()


