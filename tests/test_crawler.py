"""爬虫模块 (tactics_tools + scheduler) 单元测试。

覆盖 TacticsToolsCrawler 和 SyncScheduler 的全部公共方法及关键私有方法。
所有网络请求通过 unittest.mock 模拟，数据库使用 :memory: SQLite。
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest
from sqlalchemy import Engine, event, select

from tft_consider.crawler.scheduler import SyncScheduler
from tft_consider.crawler.tactics_tools import (
    TACTICS_TOOLS_META_URL,
    USER_AGENT,
    TacticsToolsCrawler,
    _normalize_rate,
)
from tft_consider.database import models
from tft_consider.database.models import (
    Champion,
    CompChampion,
    CompItem,
    Composition,
    Item,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session() -> Generator[models.Session, None, None]:
    """每个测试使用独立的 :memory: 数据库，teardown 中清理全局状态。"""
    event.listen(Engine, "connect", lambda dbapi_conn, _rec: dbapi_conn.execute("PRAGMA foreign_keys = ON"))
    models.init_db(":memory:")
    yield models.get_session()
    if models._engine is not None:
        models._engine.dispose()
    models._engine = None
    models._SessionLocal = None


@pytest.fixture
def sample_config() -> dict[str, Any]:
    """基础配置 fixture。"""
    return {
        "api": {"provider": "moonshot", "key": "", "model": "kimi-k2"},
        "data": {"sync_interval_hours": 6},
    }


@pytest.fixture
def sample_comps() -> list[dict[str, Any]]:
    """标准的阵容数据 fixture，包含 champions 和 items。"""
    return [
        {
            "name": "八法师",
            "tier": "S",
            "playstyle": "运营",
            "avg_placement": 2.8,
            "win_rate": 0.185,
            "play_rate": 0.052,
            "description": "强力法师阵容",
            "champions": [
                {"name": "瑞兹", "is_core": True},
                {"name": "辛德拉", "is_core": True},
                {"name": "盖伦", "is_core": False},
            ],
            "items": [
                {"champion": "瑞兹", "item": "蓝霸符", "priority": 1},
                {"champion": "瑞兹", "item": "珠光护手", "priority": 2},
                {"champion": "盖伦", "item": "狂徒铠甲", "priority": 1},
            ],
        },
        {
            "name": "六狙神",
            "tier": "A",
            "playstyle": "连胜",
            "avg_placement": 3.8,
            "win_rate": 0.152,
            "play_rate": 0.038,
            "description": "远程输出阵容",
            "champions": [
                {"name": "金克丝", "is_core": True},
                {"name": "艾希", "is_core": False},
            ],
            "items": [
                {"champion": "金克丝", "item": "无尽之刃", "priority": 1},
            ],
        },
    ]


# ---------------------------------------------------------------------------
# TacticsToolsCrawler: __init__
# ---------------------------------------------------------------------------


class TestCrawlerInit:
    """TacticsToolsCrawler.__init__ 的配置和 HTTP client 初始化。"""

    def test_init_stores_config(self, sample_config: dict[str, Any]) -> None:
        """__init__ 正确保存 config 引用。"""
        crawler = TacticsToolsCrawler(sample_config)
        assert crawler._config is sample_config

    def test_init_creates_httpx_client(self, sample_config: dict[str, Any]) -> None:
        """__init__ 创建 httpx.Client 并设置正确的 headers、timeout、follow_redirects。"""
        crawler = TacticsToolsCrawler(sample_config)
        client = crawler._client
        assert isinstance(client, httpx.Client)
        assert client.headers.get("User-Agent") == USER_AGENT
        assert client.timeout == httpx.Timeout(30.0)
        assert client.follow_redirects is True

    def test_init_user_agent_header_non_empty(self, sample_config: dict[str, Any]) -> None:
        """User-Agent 头非空字符串。"""
        crawler = TacticsToolsCrawler(sample_config)
        ua = crawler._client.headers.get("User-Agent")
        assert isinstance(ua, str)
        assert len(ua) > 0
        assert "TFT-Consider" in ua


# ---------------------------------------------------------------------------
# TacticsToolsCrawler: close()
# ---------------------------------------------------------------------------


class TestCrawlerClose:
    """TacticsToolsCrawler.close() 资源释放。"""

    def test_close_calls_client_close(self, sample_config: dict[str, Any]) -> None:
        """close() 调用 httpx.Client.close()。"""
        crawler = TacticsToolsCrawler(sample_config)
        with patch.object(crawler._client, "close") as mock_close:
            crawler.close()
            mock_close.assert_called_once()


# ---------------------------------------------------------------------------
# TacticsToolsCrawler: _fetch_page
# ---------------------------------------------------------------------------


class TestCrawlerFetchPage:
    """TacticsToolsCrawler._fetch_page 的 HTTP 请求和错误处理。"""

    def test_fetch_page_success_returns_html(self, sample_config: dict[str, Any]) -> None:
        """HTTP 200 时返回 response.text。"""
        crawler = TacticsToolsCrawler(sample_config)
        mock_response = MagicMock()
        mock_response.text = "<html>meta data</html>"
        mock_response.raise_for_status.return_value = None

        with (
            patch.object(crawler._client, "get", return_value=mock_response) as mock_get,
            patch("tft_consider.crawler.tactics_tools.time.sleep", return_value=None),
        ):
            result = crawler._fetch_page(TACTICS_TOOLS_META_URL)
            assert result == "<html>meta data</html>"
            mock_get.assert_called_once_with(TACTICS_TOOLS_META_URL)

    def test_fetch_page_http_error_returns_none(self, sample_config: dict[str, Any]) -> None:
        """httpx.HTTPError 时返回 None。"""
        crawler = TacticsToolsCrawler(sample_config)
        with (
            patch.object(crawler._client, "get", side_effect=httpx.HTTPError("timeout")),
            patch("tft_consider.crawler.tactics_tools.time.sleep", return_value=None),
        ):
            result = crawler._fetch_page(TACTICS_TOOLS_META_URL)
            assert result is None

    def test_fetch_page_generic_exception_returns_none(self, sample_config: dict[str, Any]) -> None:
        """非 HTTP 异常时也返回 None。"""
        crawler = TacticsToolsCrawler(sample_config)
        with (
            patch.object(crawler._client, "get", side_effect=OSError("network down")),
            patch("tft_consider.crawler.tactics_tools.time.sleep", return_value=None),
        ):
            result = crawler._fetch_page(TACTICS_TOOLS_META_URL)
            assert result is None

    def test_fetch_page_http_status_error_returns_none(self, sample_config: dict[str, Any]) -> None:
        """HTTP 非 2xx 状态码（raise_for_status 抛异常）时返回 None。"""
        crawler = TacticsToolsCrawler(sample_config)
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=MagicMock(status_code=404)
        )

        with (
            patch.object(crawler._client, "get", return_value=mock_response),
            patch("tft_consider.crawler.tactics_tools.time.sleep", return_value=None),
        ):
            result = crawler._fetch_page(TACTICS_TOOLS_META_URL)
            assert result is None


# ---------------------------------------------------------------------------
# TacticsToolsCrawler: _parse_comp_list
# ---------------------------------------------------------------------------


class TestCrawlerParseCompList:
    """TacticsToolsCrawler._parse_comp_list 的 HTML 解析。"""

    def test_parse_comp_list_empty_html_returns_none(self, sample_config: dict[str, Any]) -> None:
        """空 HTML 返回 None（所有解析策略均失败）。"""
        crawler = TacticsToolsCrawler(sample_config)
        result = crawler._parse_comp_list("<html><body></body></html>")
        assert result is None

    def test_parse_comp_list_no_comp_data_returns_none(self, sample_config: dict[str, Any]) -> None:
        """HTML 不包含任何阵容数据时返回 None。"""
        crawler = TacticsToolsCrawler(sample_config)
        html = "<html><body><p>No compositions here.</p></body></html>"
        result = crawler._parse_comp_list(html)
        assert result is None

    def test_parse_comp_list_with_embedded_json(self, sample_config: dict[str, Any]) -> None:
        """HTML 中包含 __NEXT_DATA__ 内嵌 JSON 时能解析出阵容。

        使用紧凑格式让第二个兜底正则正确匹配整体 JSON。
        """
        crawler = TacticsToolsCrawler(sample_config)
        html = (
            "<html><body><script>"
            'window.__NEXT_DATA__ = {"props": {"comps": [{"name": "Test Comp", "tier": "S"}]}}'
            "</script></body></html>"
        )
        result = crawler._parse_comp_list(html)
        assert result is not None
        assert len(result) == 1
        assert result[0]["name"] == "Test Comp"

    def test_parse_comp_list_with_application_json_script(self, sample_config: dict[str, Any]) -> None:
        """HTML 中包含 <script type="application/json"> 时能解析。"""
        crawler = TacticsToolsCrawler(sample_config)
        html = """<html>
        <body>
            <script type="application/json">{"name": "JSON Comp", "tier": "A"}</script>
        </body>
        </html>"""
        result = crawler._parse_comp_list(html)
        assert result is not None
        assert len(result) == 1
        assert result[0]["name"] == "JSON Comp"

    def test_parse_comp_list_with_data_tier_cards(self, sample_config: dict[str, Any]) -> None:
        """HTML 中包含 data-tier 属性卡片时能解析。"""
        crawler = TacticsToolsCrawler(sample_config)
        html = """<html>
        <body>
            <div data-tier="S" data-name="S级阵容">
                <span>胜率:55.0%</span>
                <span>登场率:20.0%</span>
                <span>平均排名:2.5</span>
            </div>
        </body>
        </html>"""
        result = crawler._parse_comp_list(html)
        assert result is not None
        assert len(result) == 1
        assert result[0]["name"] == "S级阵容"
        assert result[0]["tier"] == "S"

    def test_parse_comp_list_with_regex_fallback(self, sample_config: dict[str, Any]) -> None:
        """HTML 纯文本中可通过正则提取阵容数据。"""
        crawler = TacticsToolsCrawler(sample_config)
        html = """<html><body>
            <div>八法师 S级 胜率:18.5% 登场率:5.2% 平均排名:3.2</div>
        </body></html>"""
        result = crawler._parse_comp_list(html)
        assert result is not None
        assert len(result) == 1
        assert result[0]["name"] == "八法师"
        # avg_placement 3.2 -> tier B (<=4.5, >4.0)
        assert result[0]["tier"] in ("S", "A", "B", "C")

    def test_parse_comp_list_invalid_json_script_skipped(self, sample_config: dict[str, Any]) -> None:
        """无效 JSON 的 script 标签被跳过，不影响整体解析。"""
        crawler = TacticsToolsCrawler(sample_config)
        html = """<html>
        <body>
            <script type="application/json">not valid json {{{</script>
            <script type="application/json">{"name": "Valid Comp", "tier": "S"}</script>
        </body>
        </html>"""
        result = crawler._parse_comp_list(html)
        assert result is not None
        assert len(result) == 1
        assert result[0]["name"] == "Valid Comp"


# ---------------------------------------------------------------------------
# TacticsToolsCrawler: fetch_meta_comps
# ---------------------------------------------------------------------------


class TestCrawlerFetchMetaComps:
    """TacticsToolsCrawler.fetch_meta_comps() 的编排和容错。"""

    def test_fetch_meta_comps_when_fetch_page_returns_none(self, sample_config: dict[str, Any]) -> None:
        """_fetch_page 返回 None 时 fetch_meta_comps 返回 None。"""
        crawler = TacticsToolsCrawler(sample_config)
        with patch.object(crawler, "_fetch_page", return_value=None):
            result = crawler.fetch_meta_comps()
            assert result is None

    def test_fetch_meta_comps_when_parse_returns_none(self, sample_config: dict[str, Any]) -> None:
        """_parse_comp_list 返回 None 时 fetch_meta_comps 返回 None。"""
        crawler = TacticsToolsCrawler(sample_config)
        with (
            patch.object(crawler, "_fetch_page", return_value="<html></html>"),
            patch.object(crawler, "_parse_comp_list", return_value=None),
        ):
            result = crawler.fetch_meta_comps()
            assert result is None

    def test_fetch_meta_comps_normal_flow(
        self, sample_config: dict[str, Any], sample_comps: list[dict[str, Any]]
    ) -> None:
        """正常流程返回阵容列表。"""
        crawler = TacticsToolsCrawler(sample_config)
        with (
            patch.object(crawler, "_fetch_page", return_value="<html>mock</html>"),
            patch.object(crawler, "_parse_comp_list", return_value=sample_comps),
        ):
            result = crawler.fetch_meta_comps()
            assert result is sample_comps
            assert len(result) == 2
            assert result[0]["name"] == "八法师"

    def test_fetch_meta_comps_exception_returns_none(self, sample_config: dict[str, Any]) -> None:
        """内部抛异常时返回 None（不向上传播）。"""
        crawler = TacticsToolsCrawler(sample_config)
        with patch.object(crawler, "_fetch_page", side_effect=RuntimeError("unexpected")):
            result = crawler.fetch_meta_comps()
            assert result is None


# ---------------------------------------------------------------------------
# TacticsToolsCrawler: merge_to_database
# ---------------------------------------------------------------------------


class TestCrawlerMergeToDatabase:
    """TacticsToolsCrawler.merge_to_database() 的数据库写入和回滚。"""

    def test_merge_empty_comps_returns_zero(self, sample_config: dict[str, Any], db_session: models.Session) -> None:  # noqa: ARG002
        """空列表参数返回 0，不写入任何数据。"""
        crawler = TacticsToolsCrawler(sample_config)
        result = crawler.merge_to_database([])
        assert result == 0

    def test_merge_creates_composition_records(
        self, sample_config: dict[str, Any], sample_comps: list[dict[str, Any]], db_session: models.Session
    ) -> None:
        """正常合并后数据库中存在对应的 Composition 记录，source 为 auto_crawled。"""
        crawler = TacticsToolsCrawler(sample_config)
        result = crawler.merge_to_database(sample_comps)
        assert result == 2

        comps = db_session.execute(select(Composition)).scalars().all()
        assert len(comps) == 2

        names = {c.name for c in comps}
        assert names == {"八法师", "六狙神"}

        for c in comps:
            assert c.source == "auto_crawled"
            assert c.tier in ("S", "A")
            assert c.synced_at is not None

    def test_merge_creates_new_champions_auto(
        self, sample_config: dict[str, Any], sample_comps: list[dict[str, Any]], db_session: models.Session
    ) -> None:
        """阵容中的新 champion 自动创建到数据库，cost=0，traits="[]"。"""
        crawler = TacticsToolsCrawler(sample_config)
        crawler.merge_to_database(sample_comps)

        champions = db_session.execute(select(Champion)).scalars().all()
        names = {ch.name for ch in champions}
        # sample_comps 中有: 瑞兹, 辛德拉, 盖伦, 金克丝, 艾希
        assert "瑞兹" in names
        assert "辛德拉" in names
        assert "盖伦" in names
        assert "金克丝" in names
        assert "艾希" in names

        # 验证自动创建的 champion 默认字段
        for ch in champions:
            if ch.name == "瑞兹":
                assert ch.cost == 0
                assert ch.traits == "[]"

    def test_merge_creates_new_items_auto(
        self, sample_config: dict[str, Any], sample_comps: list[dict[str, Any]], db_session: models.Session
    ) -> None:
        """阵容中的新 item 自动创建到数据库。"""
        crawler = TacticsToolsCrawler(sample_config)
        crawler.merge_to_database(sample_comps)

        items = db_session.execute(select(Item)).scalars().all()
        item_names = {it.name for it in items}
        assert "蓝霸符" in item_names
        assert "珠光护手" in item_names
        assert "狂徒铠甲" in item_names
        assert "无尽之刃" in item_names

    def test_merge_creates_comp_champion_relations(
        self, sample_config: dict[str, Any], sample_comps: list[dict[str, Any]], db_session: models.Session
    ) -> None:
        """合并后 CompChampion 关联表记录正确。"""
        crawler = TacticsToolsCrawler(sample_config)
        crawler.merge_to_database(sample_comps)

        # 获取八法师阵容
        comp = db_session.execute(
            select(Composition).where(Composition.name == "八法师")
        ).scalar_one()

        champ_names = db_session.execute(
            select(Champion.name)
            .select_from(CompChampion)
            .join(Champion, CompChampion.champion_id == Champion.id)
            .where(CompChampion.composition_id == comp.id)
        ).scalars().all()

        assert len(champ_names) == 3
        assert "瑞兹" in champ_names
        assert "辛德拉" in champ_names
        assert "盖伦" in champ_names

        # 验证 is_core 字段
        comp_champs = db_session.execute(
            select(CompChampion).where(CompChampion.composition_id == comp.id)
        ).scalars().all()
        core_map = {}
        for cc in comp_champs:
            ch = db_session.execute(
                select(Champion).where(Champion.id == cc.champion_id)
            ).scalar_one()
            core_map[ch.name] = cc.is_core
        assert core_map.get("瑞兹") is True
        assert core_map.get("辛德拉") is True
        assert core_map.get("盖伦") is False

    def test_merge_creates_comp_item_relations(
        self, sample_config: dict[str, Any], sample_comps: list[dict[str, Any]], db_session: models.Session
    ) -> None:
        """合并后 CompItem 关联表记录正确。"""
        crawler = TacticsToolsCrawler(sample_config)
        crawler.merge_to_database(sample_comps)

        comp = db_session.execute(
            select(Composition).where(Composition.name == "八法师")
        ).scalar_one()

        item_names = db_session.execute(
            select(Item.name)
            .select_from(CompItem)
            .join(Item, CompItem.item_id == Item.id)
            .where(CompItem.composition_id == comp.id)
        ).scalars().all()

        assert len(item_names) == 3
        assert "蓝霸符" in item_names
        assert "珠光护手" in item_names
        assert "狂徒铠甲" in item_names

    def test_merge_idempotent_champions(
        self, sample_config: dict[str, Any], sample_comps: list[dict[str, Any]], db_session: models.Session
    ) -> None:
        """重复合并时 champion 不重复创建。"""
        crawler = TacticsToolsCrawler(sample_config)
        crawler.merge_to_database(sample_comps)

        # 第二次合并
        crawler2 = TacticsToolsCrawler(sample_config)
        crawler2.merge_to_database(sample_comps)

        champions = db_session.execute(select(Champion)).scalars().all()
        # 5 个不同的 champion
        assert len(champions) == 5

    def test_merge_rollback_on_exception(
        self, sample_config: dict[str, Any], sample_comps: list[dict[str, Any]], db_session: models.Session  # noqa: ARG002
    ) -> None:
        """合并过程中发生异常时回滚，session.rollback() 和 session.close() 被调用。"""
        crawler = TacticsToolsCrawler(sample_config)

        # 构建 mock session，在 flush 时抛异常
        mock_session = MagicMock()
        mock_session.flush.side_effect = RuntimeError("simulated failure")

        with patch(
            "tft_consider.crawler.tactics_tools.get_session", return_value=mock_session
        ):
            with pytest.raises(RuntimeError, match="simulated failure"):
                crawler.merge_to_database(sample_comps)

        # 验证异常后的清理行为
        mock_session.rollback.assert_called_once()
        mock_session.close.assert_called_once()

    def test_merge_exception_propagates(
        self, sample_config: dict[str, Any], sample_comps: list[dict[str, Any]], db_session: models.Session  # noqa: ARG002
    ) -> None:
        """merge_to_database 异常会向上传播（re-raise），由调用方处理。"""
        crawler = TacticsToolsCrawler(sample_config)
        with patch.object(crawler, "_load_champion_map", side_effect=RuntimeError("init failure")):
            with pytest.raises(RuntimeError, match="init failure"):
                crawler.merge_to_database(sample_comps)


# ---------------------------------------------------------------------------
# TacticsToolsCrawler: _validate_comp_data
# ---------------------------------------------------------------------------


class TestValidateCompData:
    """TacticsToolsCrawler._validate_comp_data 的数据校验。"""

    def test_valid_comp_data_passes(self) -> None:
        """name 有效且 tier 合法，返回 True。"""
        comp = {"name": "测试阵容", "tier": "S"}
        assert TacticsToolsCrawler._validate_comp_data(comp) is True

    def test_valid_comp_without_tier_passes(self) -> None:
        """无 tier 字段时也通过（tier 可选）。"""
        comp: dict[str, Any] = {"name": "测试阵容"}
        assert TacticsToolsCrawler._validate_comp_data(comp) is True

    def test_empty_tier_passes(self) -> None:
        """空 tier 通过。"""
        comp = {"name": "测试阵容", "tier": ""}
        assert TacticsToolsCrawler._validate_comp_data(comp) is True

    def test_missing_name_fails(self) -> None:
        """无 name 字段返回 False。"""
        comp = {"tier": "S"}
        assert TacticsToolsCrawler._validate_comp_data(comp) is False

    def test_invalid_tier_fails(self) -> None:
        """tier 不是合法的 S/A/B/C/D 返回 False。"""
        comp = {"name": "测试阵容", "tier": "X"}
        assert TacticsToolsCrawler._validate_comp_data(comp) is False

    def test_lowercase_tier_passess_uppercase(self) -> None:
        """小写 tier 也能通过（校验做了 upper()）。"""
        comp = {"name": "测试阵容", "tier": "s"}
        assert TacticsToolsCrawler._validate_comp_data(comp) is True

    def test_tier_d_valid(self) -> None:
        """tier D 合法。"""
        comp = {"name": "弱阵容", "tier": "D"}
        assert TacticsToolsCrawler._validate_comp_data(comp) is True


# ---------------------------------------------------------------------------
# TacticsToolsCrawler: _infer_tier_from_position
# ---------------------------------------------------------------------------


class TestInferTierFromPosition:
    """TacticsToolsCrawler._infer_tier_from_position 的 tier 推断逻辑。"""

    def test_avg_placement_le_3_5_returns_s(self) -> None:
        """avg_placement <= 3.5 -> S。"""
        assert TacticsToolsCrawler._infer_tier_from_position(3.0) == "S"
        assert TacticsToolsCrawler._infer_tier_from_position(3.5) == "S"

    def test_avg_placement_le_4_0_returns_a(self) -> None:
        """3.5 < avg_placement <= 4.0 -> A。"""
        assert TacticsToolsCrawler._infer_tier_from_position(3.6) == "A"
        assert TacticsToolsCrawler._infer_tier_from_position(4.0) == "A"

    def test_avg_placement_le_4_5_returns_b(self) -> None:
        """4.0 < avg_placement <= 4.5 -> B。"""
        assert TacticsToolsCrawler._infer_tier_from_position(4.1) == "B"
        assert TacticsToolsCrawler._infer_tier_from_position(4.5) == "B"

    def test_avg_placement_gt_4_5_returns_c(self) -> None:
        """avg_placement > 4.5 -> C。"""
        assert TacticsToolsCrawler._infer_tier_from_position(4.6) == "C"
        assert TacticsToolsCrawler._infer_tier_from_position(5.0) == "C"


# ---------------------------------------------------------------------------
# _normalize_rate
# ---------------------------------------------------------------------------


class TestNormalizeRate:
    """_normalize_rate 百分比字符串转换。"""

    def test_rate_over_1_divides_by_100(self) -> None:
        """>1 的值除以 100。"""
        assert _normalize_rate("55.0") == 0.55
        assert _normalize_rate("100") == 1.0
        assert _normalize_rate("18.5") == 0.185

    def test_rate_under_1_remains_unchanged(self) -> None:
        """<=1 的值保持不变。"""
        assert _normalize_rate("0.185") == 0.185
        assert _normalize_rate("0.5") == 0.5
        assert _normalize_rate("1.0") == 1.0

    def test_invalid_rate_returns_zero(self) -> None:
        """无法解析的字符串返回 0.0。"""
        assert _normalize_rate("abc") == 0.0
        assert _normalize_rate("") == 0.0

    def test_rate_exactly_one(self) -> None:
        """值正好为 1 保持不变。"""
        assert _normalize_rate("1") == 1.0


# ---------------------------------------------------------------------------
# SyncScheduler: __init__
# ---------------------------------------------------------------------------


class TestSchedulerInit:
    """SyncScheduler.__init__ 的配置读取。"""

    def test_init_reads_sync_interval_from_config(self) -> None:
        """从 config["data"]["sync_interval_hours"] 读取间隔。"""
        config = {"data": {"sync_interval_hours": 12}}
        scheduler = SyncScheduler(config)
        assert scheduler._interval_hours == 12.0

    def test_init_default_interval_when_missing(self) -> None:
        """缺少 data 键时使用默认值 6.0。"""
        config: dict[str, Any] = {}
        scheduler = SyncScheduler(config)
        assert scheduler._interval_hours == 6.0

    def test_init_default_interval_when_data_not_dict(self) -> None:
        """data 不是 dict 时使用默认值 6.0。"""
        config = {"data": "invalid"}
        scheduler = SyncScheduler(config)
        assert scheduler._interval_hours == 6.0

    def test_init_default_interval_when_key_missing(self) -> None:
        """sync_interval_hours 键缺失时使用默认值 6.0。"""
        config: dict[str, Any] = {"data": {}}
        scheduler = SyncScheduler(config)
        assert scheduler._interval_hours == 6.0

    def test_init_float_interval_from_string(self) -> None:
        """sync_interval_hours 为字符串时转为 float。"""
        config = {"data": {"sync_interval_hours": "3.5"}}
        scheduler = SyncScheduler(config)
        assert scheduler._interval_hours == 3.5

    def test_init_creates_crawler_instance(self) -> None:
        """__init__ 创建 TacticsToolsCrawler 实例。"""
        config = {"data": {"sync_interval_hours": 6}}
        scheduler = SyncScheduler(config)
        from tft_consider.crawler.tactics_tools import TacticsToolsCrawler

        assert isinstance(scheduler._crawler, TacticsToolsCrawler)


# ---------------------------------------------------------------------------
# SyncScheduler: sync_now
# ---------------------------------------------------------------------------


class TestSchedulerSyncNow:
    """SyncScheduler.sync_now() 的同步逻辑和容错。"""

    def test_sync_now_returns_false_when_crawler_returns_none(self, sample_config: dict[str, Any]) -> None:
        """crawler.fetch_meta_comps 返回 None 时 sync_now 返回 False。"""
        with patch.object(TacticsToolsCrawler, "fetch_meta_comps", return_value=None):
            scheduler = SyncScheduler(sample_config)
            result = scheduler.sync_now()
            assert result is False

    def test_sync_now_returns_false_when_comps_empty(self, sample_config: dict[str, Any]) -> None:
        """crawler.fetch_meta_comps 返回空列表时 sync_now 返回 False（merge 返回 0）。"""
        with (
            patch.object(TacticsToolsCrawler, "fetch_meta_comps", return_value=[]),
            patch.object(TacticsToolsCrawler, "merge_to_database", return_value=0),
        ):
            scheduler = SyncScheduler(sample_config)
            result = scheduler.sync_now()
            assert result is False

    def test_sync_now_returns_true_on_success(
        self, sample_config: dict[str, Any], sample_comps: list[dict[str, Any]]
    ) -> None:
        """正常同步成功返回 True。"""
        with (
            patch.object(TacticsToolsCrawler, "fetch_meta_comps", return_value=sample_comps),
            patch.object(TacticsToolsCrawler, "merge_to_database", return_value=2),
        ):
            scheduler = SyncScheduler(sample_config)
            result = scheduler.sync_now()
            assert result is True

    def test_sync_now_exception_returns_false(self, sample_config: dict[str, Any]) -> None:
        """同步过程中异常时返回 False（不抛异常）。"""
        with patch.object(TacticsToolsCrawler, "fetch_meta_comps", side_effect=RuntimeError("crash")):
            scheduler = SyncScheduler(sample_config)
            result = scheduler.sync_now()
            assert result is False

    def test_sync_now_merge_exception_returns_false(
        self, sample_config: dict[str, Any], sample_comps: list[dict[str, Any]]
    ) -> None:
        """merge_to_database 抛异常时 sync_now 返回 False。"""
        with (
            patch.object(TacticsToolsCrawler, "fetch_meta_comps", return_value=sample_comps),
            patch.object(TacticsToolsCrawler, "merge_to_database", side_effect=RuntimeError("db error")),
        ):
            scheduler = SyncScheduler(sample_config)
            result = scheduler.sync_now()
            assert result is False


# ---------------------------------------------------------------------------
# SyncScheduler: start / stop 生命周期
# ---------------------------------------------------------------------------


class TestSchedulerLifecycle:
    """SyncScheduler.start() / stop() 的生命周期管理。"""

    def test_start_no_exception(self, sample_config: dict[str, Any]) -> None:
        """start() 不抛异常。"""
        with patch("tft_consider.crawler.scheduler.threading.Timer") as mock_timer_cls:
            scheduler = SyncScheduler(sample_config)
            scheduler.start()
            assert scheduler._running is True
            mock_timer_cls.assert_called_once()

    def test_stop_no_exception_when_timer_is_none(self, sample_config: dict[str, Any]) -> None:
        """start 未调用时 stop() 不抛异常（timer 为 None）。"""
        scheduler = SyncScheduler(sample_config)
        scheduler.stop()
        assert scheduler._running is False

    def test_start_stop_sequential(self, sample_config: dict[str, Any]) -> None:
        """start() 后 stop() 连续调用不抛异常。"""
        with patch("tft_consider.crawler.scheduler.threading.Timer") as mock_timer_cls:
            mock_timer = MagicMock()
            mock_timer_cls.return_value = mock_timer

            scheduler = SyncScheduler(sample_config)
            scheduler.start()
            assert scheduler._running is True

            scheduler.stop()
            assert scheduler._running is False
            mock_timer.cancel.assert_called_once()
            assert scheduler._timer is None

    def test_start_called_twice_is_noop(self, sample_config: dict[str, Any]) -> None:
        """重复调用 start() 不创建第二个定时器。"""
        with patch("tft_consider.crawler.scheduler.threading.Timer") as mock_timer_cls:
            scheduler = SyncScheduler(sample_config)
            scheduler.start()
            call_count = mock_timer_cls.call_count
            scheduler.start()
            # 第二次 start() 应该因 _running 已为 True 直接返回
            assert mock_timer_cls.call_count == call_count

    def test_start_with_zero_interval_no_timer(self) -> None:
        """interval_hours <= 0 时不启动定时器。"""
        config = {"data": {"sync_interval_hours": 0}}
        with patch("tft_consider.crawler.scheduler.threading.Timer") as mock_timer_cls:
            scheduler = SyncScheduler(config)
            scheduler.start()
            assert scheduler._running is False
            mock_timer_cls.assert_not_called()

    def test_start_with_negative_interval_no_timer(self) -> None:
        """interval_hours 为负数时不启动定时器。"""
        config = {"data": {"sync_interval_hours": -1.0}}
        with patch("tft_consider.crawler.scheduler.threading.Timer") as mock_timer_cls:
            scheduler = SyncScheduler(config)
            scheduler.start()
            assert scheduler._running is False
            mock_timer_cls.assert_not_called()


# ---------------------------------------------------------------------------
# SyncScheduler: _on_timer
# ---------------------------------------------------------------------------


class TestSchedulerOnTimer:
    """SyncScheduler._on_timer 定时器回调。"""

    def test_on_timer_calls_sync_now(self, sample_config: dict[str, Any]) -> None:
        """_on_timer 调用 sync_now。"""
        with patch.object(TacticsToolsCrawler, "fetch_meta_comps", return_value=[]):
            scheduler = SyncScheduler(sample_config)
            with patch.object(scheduler, "sync_now") as mock_sync_now:
                scheduler._running = True
                scheduler._on_timer()
                mock_sync_now.assert_called_once()

    def test_on_timer_schedules_next_when_running(self, sample_config: dict[str, Any]) -> None:
        """sync_now 结束后如果 _running 仍为 True，安排下一次同步。"""
        with patch.object(TacticsToolsCrawler, "fetch_meta_comps", return_value=[]):
            scheduler = SyncScheduler(sample_config)
            scheduler._running = True
            with patch.object(scheduler, "_schedule_next") as mock_schedule:
                scheduler._on_timer()
                mock_schedule.assert_called_once()

    def test_on_timer_no_reschedule_when_stopped(self, sample_config: dict[str, Any]) -> None:
        """如果 _running 为 False，不安排下一次同步。"""
        with patch.object(TacticsToolsCrawler, "fetch_meta_comps", return_value=[]):
            scheduler = SyncScheduler(sample_config)
            scheduler._running = False
            with patch.object(scheduler, "sync_now"), patch.object(scheduler, "_schedule_next") as mock_schedule:
                scheduler._on_timer()
                mock_schedule.assert_not_called()
