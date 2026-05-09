"""SQLAlchemy ORM 模型定义。

定义数据库 schema、初始化连接和会话获取。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    sessionmaker,
)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""

    pass


class Meta(Base):
    """数据库元信息表。存储 set/patch 等全局键值对。"""

    __tablename__ = "meta"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True)
    value: Mapped[str] = mapped_column(Text)


class SchemaVersion(Base):
    """数据库 schema 版本迁移追踪表。"""

    __tablename__ = "schema_version"

    version: Mapped[int] = mapped_column(primary_key=True)
    applied_at: Mapped[datetime]
    description: Mapped[str] = mapped_column(String(200))


class Composition(Base):
    """阵容表。存储一个完整阵容的名称、强度、站位等信息。"""

    __tablename__ = "compositions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    tier: Mapped[str] = mapped_column(String(10))  # "S"|"A"|"B"|"C"
    difficulty: Mapped[str] = mapped_column(String(20))  # "easy"|"medium"|"hard"
    playstyle: Mapped[str] = mapped_column(String(50))  # "连胜"|"连败"|"赌狗"|"速八"|"运营"
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="manual")  # "manual"|"auto_crawled"
    synced_at: Mapped[datetime | None]
    # 站位 JSON (4x7 grid): [{"champion": "...", "row": 0, "col": 3}, ...]
    positioning: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string


class Champion(Base):
    """棋子表。存储单个棋子的名称、费用、羁绊等信息。"""

    __tablename__ = "champions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    cost: Mapped[int]  # 1-5 费卡
    traits: Mapped[str] = mapped_column(Text)  # JSON list of trait names
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)


class Item(Base):
    """装备表。存储单个装备的名称、合成配方、效果。"""

    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    components: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list of base items
    effect: Mapped[str | None] = mapped_column(Text, nullable=True)


class Synergy(Base):
    """羁绊表。存储羁绊名称、断点、各层效果。"""

    __tablename__ = "synergies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    breakpoints: Mapped[str] = mapped_column(Text)  # JSON list, e.g. [2, 4, 6]
    effect_per_level: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON


class CompChampion(Base):
    """阵容-棋子关联表。记录阵容中包含哪些棋子及核心/星级/站位。"""

    __tablename__ = "comp_champions"

    id: Mapped[int] = mapped_column(primary_key=True)
    composition_id: Mapped[int] = mapped_column(ForeignKey("compositions.id"))
    champion_id: Mapped[int] = mapped_column(ForeignKey("champions.id"))
    is_core: Mapped[bool] = mapped_column(Boolean, default=False)
    star_target: Mapped[int] = mapped_column(Integer, default=2)
    position: Mapped[str | None] = mapped_column(String(10), nullable=True)  # "row,col"


class CompItem(Base):
    """阵容-装备关联表。记录阵容中推荐哪些装备以及优先级。"""

    __tablename__ = "comp_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    composition_id: Mapped[int] = mapped_column(ForeignKey("compositions.id"))
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"))
    champion_id: Mapped[int | None] = mapped_column(ForeignKey("champions.id"), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=1)  # 1=最高优先级


# 模块级全局变量，由 init_db() 初始化
_engine: Any = None
_SessionLocal: sessionmaker[Session] | None = None


def init_db(db_path: str | None = None) -> None:
    """初始化数据库连接。

    Args:
        db_path: SQLite 数据库文件路径。为 None 时自动使用 config 目录下的
                 data/tft_consider.db。

    创建 engine、SessionLocal 和所有表（如果不存在）。
    """
    global _engine, _SessionLocal

    if db_path is None:
        from tft_consider.config import _config_dir

        db_dir = _config_dir() / "data"
        db_dir.mkdir(parents=True, exist_ok=True)
        db_path = str(db_dir / "tft_consider.db")

    _engine = create_engine(f"sqlite:///{db_path}")
    _SessionLocal = sessionmaker(bind=_engine)
    Base.metadata.create_all(_engine)


def get_session() -> Session:
    """获取一个新的数据库会话。

    Returns:
        一个新的 SQLAlchemy Session 实例。

    Raises:
        RuntimeError: 如果数据库尚未通过 init_db() 初始化。
    """
    if _SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _SessionLocal()
