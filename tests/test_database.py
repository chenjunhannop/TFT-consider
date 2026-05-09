"""数据库模块 (models + importer) 单元测试。

覆盖 init_db、get_session、所有 ORM 模型的约束和字段、
以及 import_from_json 的完整导入流程。
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy import Engine, event, inspect, select
from sqlalchemy.exc import IntegrityError

from tft_consider.database import importer, models
from tft_consider.database.models import (
    Champion,
    CompChampion,
    CompItem,
    Composition,
    Item,
    Meta,
    SchemaVersion,
    Synergy,
    get_session,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session() -> Generator[models.Session, None, None]:
    """每个测试使用独立的 :memory: 数据库。

    在 teardown 中清理 module-level 全局状态，确保测试隔离。
    """
    # SQLite 默认不强制外键约束。在 Engine 类级别注册 connect 事件，
    # 确保 init_db 及其后续所有连接都启用外键约束。
    event.listen(Engine, "connect", lambda dbapi_conn, _rec: dbapi_conn.execute("PRAGMA foreign_keys = ON"))
    models.init_db(":memory:")
    yield models.get_session()
    # 清理全局状态，防止测试间泄漏
    if models._engine is not None:
        models._engine.dispose()
    models._engine = None
    models._SessionLocal = None


@pytest.fixture
def example_json_path(tmp_path: Path) -> Path:
    """将 example_comps.json 复制到临时目录并返回路径。"""
    src = Path(__file__).parent.parent / "data" / "templates" / "example_comps.json"
    dest = tmp_path / "example_comps.json"
    shutil.copy(src, dest)
    return dest


# ---------------------------------------------------------------------------
# TestModels: init_db / get_session
# ---------------------------------------------------------------------------


class TestInitDbAndSession:
    """init_db 和 get_session 的基本行为。"""

    def test_init_db_creates_tables(self, db_session: models.Session) -> None:
        """init_db(":memory:") 后所有 8 个表都存在。"""
        inspector = inspect(db_session.get_bind())
        table_names = inspector.get_table_names()
        expected = {
            "meta",
            "schema_version",
            "compositions",
            "champions",
            "items",
            "synergies",
            "comp_champions",
            "comp_items",
            "game_replays",
        }
        assert set(table_names) == expected

    def test_get_session_without_init(self) -> None:
        """未调用 init_db 时 get_session() 抛出 RuntimeError。"""
        # 确保当前测试没有残留的全局状态
        models._engine = None
        models._SessionLocal = None
        with pytest.raises(RuntimeError, match="Database not initialized"):
            get_session()


# ---------------------------------------------------------------------------
# TestModels: 唯一约束
# ---------------------------------------------------------------------------


class TestUniqueConstraints:
    """Champion / Item / Synergy 的 name 唯一约束。"""

    def test_champion_unique_constraint(self, db_session: models.Session) -> None:
        """同名 champion INSERT 第二次抛出 IntegrityError。"""
        c1 = Champion(name="艾希", cost=1, traits="[]")
        db_session.add(c1)
        db_session.commit()

        c2 = Champion(name="艾希", cost=2, traits='["狙神"]')
        db_session.add(c2)
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_item_unique_constraint(self, db_session: models.Session) -> None:
        """同名 item INSERT 第二次抛出 IntegrityError。"""
        i1 = Item(name="无尽之刃")
        db_session.add(i1)
        db_session.commit()

        i2 = Item(name="无尽之刃", components="[]")
        db_session.add(i2)
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_synergy_unique_constraint(self, db_session: models.Session) -> None:
        """同名 synergy INSERT 第二次抛出 IntegrityError。"""
        s1 = Synergy(name="法师", breakpoints="[2,4,6]")
        db_session.add(s1)
        db_session.commit()

        s2 = Synergy(name="法师", breakpoints="[2,4,6,8]")
        db_session.add(s2)
        with pytest.raises(IntegrityError):
            db_session.commit()


# ---------------------------------------------------------------------------
# TestModels: Composition 字段
# ---------------------------------------------------------------------------


class TestCompositionFields:
    """Composition 模型字段类型与默认值。"""

    def test_composition_field_types(self, db_session: models.Session) -> None:
        """Composition 字段类型正确，nullable 字段可接受 None。"""
        comp = Composition(
            name="测试阵容",
            tier="S",
            difficulty="medium",
            playstyle="运营",
            description=None,
            source="manual",
            synced_at=None,
            positioning=None,
        )
        db_session.add(comp)
        db_session.commit()

        # 从数据库回读
        result = db_session.execute(
            select(Composition).where(Composition.name == "测试阵容")
        ).scalar_one()
        assert result.name == "测试阵容"
        assert result.tier == "S"
        assert result.difficulty == "medium"
        assert result.playstyle == "运营"
        assert result.description is None
        assert result.source == "manual"
        assert result.synced_at is None
        assert result.positioning is None


# ---------------------------------------------------------------------------
# TestModels: 外键约束
# ---------------------------------------------------------------------------


class TestForeignKeyConstraints:
    """CompChampion / CompItem 外键约束。"""

    def test_comp_champion_foreign_key(self, db_session: models.Session) -> None:
        """comp_champion 引用不存在的 composition_id 时失败。"""
        cc = CompChampion(composition_id=9999, champion_id=1)
        db_session.add(cc)
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_comp_item_foreign_key(self, db_session: models.Session) -> None:
        """comp_item 引用不存在的 item_id 时失败。"""
        ci = CompItem(composition_id=1, item_id=9999)
        db_session.add(ci)
        with pytest.raises(IntegrityError):
            db_session.commit()


# ---------------------------------------------------------------------------
# TestModels: Meta 与 SchemaVersion
# ---------------------------------------------------------------------------


class TestMetaTable:
    """Meta 表键值存储。"""

    def test_meta_table_set_get(self, db_session: models.Session) -> None:
        """meta 表可以设置和读取 key-value。"""
        db_session.add(Meta(key="set", value="14"))
        db_session.add(Meta(key="patch", value="14.10"))
        db_session.commit()

        result_set = db_session.execute(
            select(Meta.value).where(Meta.key == "set")
        ).scalar_one()
        assert result_set == "14"

        result_patch = db_session.execute(
            select(Meta.value).where(Meta.key == "patch")
        ).scalar_one()
        assert result_patch == "14.10"


class TestSchemaVersionTable:
    """SchemaVersion 表基本操作。"""

    def test_schema_version_table(self, db_session: models.Session) -> None:
        """schema_version 表可以 INSERT 一条记录。"""
        from datetime import UTC, datetime

        sv = SchemaVersion(version=1, applied_at=datetime.now(UTC), description="init")
        db_session.add(sv)
        db_session.commit()

        result = db_session.execute(
            select(SchemaVersion).where(SchemaVersion.version == 1)
        ).scalar_one()
        assert result.version == 1
        assert result.description == "init"


# ---------------------------------------------------------------------------
# TestImporter: 基本导入流程
# ---------------------------------------------------------------------------


class TestImportBasic:
    """import_from_json 基本流程与计数验证。"""

    def test_import_from_json_basic(self, example_json_path: Path, db_session: models.Session) -> None:
        """从 example_comps.json 导入，验证返回的计数。"""
        stats = importer.import_from_json(example_json_path)
        assert stats["imported"]["compositions"] == 2
        assert stats["imported"]["champions"] == 14
        assert stats["imported"]["items"] == 10
        assert stats["imported"]["synergies"] == 6
        # 首次导入没有 skip
        assert stats["skipped"]["champions"] == 0
        assert stats["skipped"]["items"] == 0
        assert stats["skipped"]["synergies"] == 0

    def test_import_champions_count(self, example_json_path: Path, db_session: models.Session) -> None:
        """导入后 champions 表有 14 条记录。"""
        importer.import_from_json(example_json_path)
        count = db_session.execute(
            select(Champion)
        ).scalars().all()
        assert len(list(count)) == 14

    def test_import_items_count(self, example_json_path: Path, db_session: models.Session) -> None:
        """导入后 items 表有 10 条记录。"""
        importer.import_from_json(example_json_path)
        items = db_session.execute(select(Item)).scalars().all()
        assert len(list(items)) == 10

    def test_import_synergies_count(self, example_json_path: Path, db_session: models.Session) -> None:
        """导入后 synergies 表有 6 条记录。"""
        importer.import_from_json(example_json_path)
        synergies = db_session.execute(select(Synergy)).scalars().all()
        assert len(list(synergies)) == 6

    def test_import_compositions_count(self, example_json_path: Path, db_session: models.Session) -> None:
        """导入后 compositions 表有 2 条记录。"""
        importer.import_from_json(example_json_path)
        compositions = db_session.execute(select(Composition)).scalars().all()
        assert len(list(compositions)) == 2


# ---------------------------------------------------------------------------
# TestImporter: 关联表
# ---------------------------------------------------------------------------


class TestImportRelations:
    """import_from_json 后关联表的正确性。"""

    def test_import_comp_champions_relation(self, example_json_path: Path, db_session: models.Session) -> None:
        """comp_champions 关联正确，可通过 composition 查到其棋子。"""
        importer.import_from_json(example_json_path)

        # 查找 "八法师" 阵容
        comp = db_session.execute(
            select(Composition).where(Composition.name == "八法师")
        ).scalar_one()

        # 通过关联表查出该阵容的所有棋子名称
        champ_names = db_session.execute(
            select(Champion.name)
            .select_from(CompChampion)
            .join(Champion, CompChampion.champion_id == Champion.id)
            .where(CompChampion.composition_id == comp.id)
        ).scalars().all()

        # "八法师" 阵容应有 9 个棋子关联记录
        assert len(champ_names) == 9
        assert "瑞兹" in champ_names
        assert "辛德拉" in champ_names
        assert "盖伦" in champ_names

    def test_import_comp_items_relation(self, example_json_path: Path, db_session: models.Session) -> None:
        """comp_items 关联正确，可查到阵容的装备。"""
        importer.import_from_json(example_json_path)

        # 查找 "八法师" 阵容
        comp = db_session.execute(
            select(Composition).where(Composition.name == "八法师")
        ).scalar_one()

        # 通过关联表查出该阵容的所有装备名称
        item_names = db_session.execute(
            select(Item.name)
            .select_from(CompItem)
            .join(Item, CompItem.item_id == Item.id)
            .where(CompItem.composition_id == comp.id)
        ).scalars().all()

        # "八法师" 阵容应有 9 条装备记录
        assert len(item_names) == 9
        assert "蓝霸符" in item_names
        assert "珠光护手" in item_names
        assert "狂徒铠甲" in item_names


# ---------------------------------------------------------------------------
# TestImporter: 幂等导入
# ---------------------------------------------------------------------------


class TestImportIdempotent:
    """重复导入的去重行为。"""

    def test_import_idempotent_champions(self, example_json_path: Path, db_session: models.Session) -> None:
        """两次导入，champions 不重复（只保持 14 条）。"""
        importer.import_from_json(example_json_path)
        stats2 = importer.import_from_json(example_json_path)

        # 第二次导入 champions 全部 skip
        assert stats2["imported"]["champions"] == 0
        assert stats2["skipped"]["champions"] == 14

        # 数据库仍为 14 条
        champions = db_session.execute(select(Champion)).scalars().all()
        assert len(list(champions)) == 14

    def test_import_idempotent_items(self, example_json_path: Path, db_session: models.Session) -> None:
        """两次导入，items 不重复（只保持 10 条）。"""
        importer.import_from_json(example_json_path)
        stats2 = importer.import_from_json(example_json_path)

        assert stats2["imported"]["items"] == 0
        assert stats2["skipped"]["items"] == 10

        items = db_session.execute(select(Item)).scalars().all()
        assert len(list(items)) == 10


# ---------------------------------------------------------------------------
# TestImporter: Meta 表更新
# ---------------------------------------------------------------------------


class TestImportMeta:
    """import_from_json 后 meta 表的 set/patch 更新。"""

    def test_import_meta_updated(self, example_json_path: Path, db_session: models.Session) -> None:
        """导入后 meta 表有正确的 set 和 patch 值。"""
        importer.import_from_json(example_json_path)

        set_value = db_session.execute(
            select(Meta.value).where(Meta.key == "set")
        ).scalar_one()
        assert set_value == "14"

        patch_value = db_session.execute(
            select(Meta.value).where(Meta.key == "patch")
        ).scalar_one()
        assert patch_value == "14.10"


# ---------------------------------------------------------------------------
# TestImporter: 错误处理
# ---------------------------------------------------------------------------


class TestImportErrors:
    """import_from_json 的错误处理。"""

    def test_import_file_not_found(self, db_session: models.Session) -> None:
        """不存在的 JSON 文件，抛出 FileNotFoundError。"""
        nonexistent = Path("/nonexistent/path/comps.json")
        with pytest.raises(FileNotFoundError, match="JSON file not found"):
            importer.import_from_json(nonexistent)

    def test_import_invalid_json(self, tmp_path: Path, db_session: models.Session) -> None:
        """无效 JSON 文件，抛出异常。"""
        bad_json = tmp_path / "bad.json"
        bad_json.write_text("this is not json {{{", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            importer.import_from_json(bad_json)
