"""Tactics.tools Meta 数据爬虫。

从 tactics.tools 爬取当前版本的 meta 阵容数据，并合并到本地 SQLite 数据库。
爬取采用 best-effort 策略：失败时返回 None，不影响工具正常运行。
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import UTC, datetime
from typing import Any

import httpx
from bs4 import BeautifulSoup

from tft_consider.database.models import (
    Champion,
    CompChampion,
    CompItem,
    Composition,
    Item,
    get_session,
)

logger = logging.getLogger(__name__)

USER_AGENT = "TFT-Consider/0.1.0 (Open Source TFT Analysis Tool)"
REQUEST_INTERVAL = 2.0  # 请求间隔（秒）

# tactics.tools 基础 URL
TACTICS_TOOLS_BASE = "https://tactics.tools"
TACTICS_TOOLS_META_URL = f"{TACTICS_TOOLS_BASE}/zh/meta"


class TacticsToolsCrawler:
    """从 tactics.tools 爬取当前版本的 meta 阵容数据。

    设计为可扩展的爬虫基类模式，后续可添加新数据源。
    爬取采用 best-effort 策略：失败时返回 None，不影响工具正常运行。
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """初始化爬虫。

        Args:
            config: 应用配置字典。
        """
        self._config = config
        self._client = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=30.0,
            follow_redirects=True,
        )

    def fetch_meta_comps(self) -> list[dict[str, Any]] | None:
        """爬取当前版本的 meta 阵容列表。

        Returns:
            meta 阵容数据列表，爬取失败时返回 None。
            每个阵容数据结构为：
            {
                "name": str,
                "tier": str,
                "playstyle": str,
                "avg_placement": float,
                "win_rate": float,
                "play_rate": float,
                "description": str | None,
                "champions": [{"name": str, "is_core": bool}, ...],
                "items": [{"champion": str, "item": str, "priority": int}, ...],
            }
        """
        try:
            logger.info("开始爬取 tactics.tools meta 数据...")
            html = self._fetch_page(TACTICS_TOOLS_META_URL)
            if html is None:
                logger.warning("无法获取 tactics.tools 页面内容")
                return None

            comps = self._parse_comp_list(html)
            if comps is None:
                logger.warning("无法从 HTML 中解析阵容数据")
                return None

            logger.info("成功爬取 %d 个阵容", len(comps))
            return comps
        except Exception:
            logger.exception("爬取 tactics.tools 时发生未预期错误")
            return None

    def merge_to_database(self, comps: list[dict[str, Any]]) -> int:
        """将爬取的 meta 阵容写入 SQLite 数据库。

        Args:
            comps: fetch_meta_comps() 返回的阵容数据列表。

        Returns:
            成功写入的阵容数量。
        """
        if not comps:
            logger.info("没有阵容数据需要合并")
            return 0

        session = get_session()
        merged_count = 0
        now = datetime.now(tz=UTC).replace(tzinfo=None)

        try:
            # 预加载已存在的 champion 和 item 名称映射
            champion_name_to_id = self._load_champion_map(session)
            item_name_to_id = self._load_item_map(session)

            new_champions_added = 0
            new_items_added = 0

            for comp_data in comps:
                # 先确保阵容中的 champion 和 item 在数据库中存在
                for champ_info in comp_data.get("champions", []):
                    name = champ_info["name"]
                    if name not in champion_name_to_id:
                        champion = Champion(name=name, cost=0, traits="[]")
                        session.add(champion)
                        session.flush()
                        champion_name_to_id[name] = champion.id
                        new_champions_added += 1

                for item_info in comp_data.get("items", []):
                    item_name = item_info["item"]
                    if item_name not in item_name_to_id:
                        item = Item(name=item_name)
                        session.add(item)
                        session.flush()
                        item_name_to_id[item_name] = item.id
                        new_items_added += 1

                # 创建阵容记录
                composition = Composition(
                    name=comp_data["name"],
                    tier=comp_data.get("tier", "B"),
                    difficulty="medium",
                    playstyle=comp_data.get("playstyle", "运营"),
                    description=comp_data.get("description"),
                    source="auto_crawled",
                    synced_at=now,
                )
                session.add(composition)
                session.flush()

                # 关联棋子
                for champ_info in comp_data.get("champions", []):
                    champion_id = champion_name_to_id.get(champ_info["name"])
                    if champion_id is None:
                        continue
                    comp_champion = CompChampion(
                        composition_id=composition.id,
                        champion_id=champion_id,
                        is_core=champ_info.get("is_core", False),
                    )
                    session.add(comp_champion)

                # 关联装备
                for item_info in comp_data.get("items", []):
                    item_id = item_name_to_id.get(item_info["item"])
                    if item_id is None:
                        continue
                    champion_id = champion_name_to_id.get(item_info.get("champion"))
                    comp_item = CompItem(
                        composition_id=composition.id,
                        item_id=item_id,
                        champion_id=champion_id,
                        priority=item_info.get("priority", 1),
                    )
                    session.add(comp_item)

                merged_count += 1

            session.commit()

            if new_champions_added > 0:
                logger.info("自动创建了 %d 个新棋子记录", new_champions_added)
            if new_items_added > 0:
                logger.info("自动创建了 %d 个新装备记录", new_items_added)
            logger.info("成功合并 %d 个阵容到数据库", merged_count)

        except Exception:
            session.rollback()
            logger.exception("合并阵容数据到数据库时发生错误")
            raise
        finally:
            session.close()

        return merged_count

    # --- 私有方法 ---

    def _fetch_page(self, url: str) -> str | None:
        """获取指定 URL 的 HTML 内容。

        Args:
            url: 要请求的页面 URL。

        Returns:
            HTML 文本内容，请求失败时返回 None。
        """
        try:
            logger.debug("请求 URL: %s", url)
            response = self._client.get(url)
            response.raise_for_status()
            # 请求间隔控制
            time.sleep(REQUEST_INTERVAL)
            return response.text
        except httpx.HTTPError as e:
            logger.warning("HTTP 请求失败 (%s): %s", url, e)
            return None
        except Exception:
            logger.exception("请求页面时发生未预期错误: %s", url)
            return None

    def _parse_comp_list(self, html: str) -> list[dict[str, Any]] | None:
        """从 HTML 中提取阵容数据。

        采用多层解析策略：
        1. 尝试从内嵌 JSON/script 标签提取结构化数据
        2. 使用 BeautifulSoup 解析 HTML 结构
        3. 正则表达式兜底提取文本中的关键字段

        Args:
            html: tactics.tools 页面的 HTML 内容。

        Returns:
            解析出的阵容数据列表，无法解析时返回 None。
        """
        soup = BeautifulSoup(html, "html.parser")

        # --- 策略 1: 尝试从 script 标签中提取内嵌 JSON ---
        comps = self._try_extract_embedded_json(soup)
        if comps:
            logger.debug("通过内嵌 JSON 解析到 %d 个阵容", len(comps))
            return comps

        # --- 策略 2: 通过 HTML 结构解析 ---
        comps = self._try_parse_html_structure(soup)
        if comps:
            logger.debug("通过 HTML 结构解析到 %d 个阵容", len(comps))
            return comps

        # --- 策略 3: 正则表达式兜底 ---
        comps = self._try_regex_extraction(html)
        if comps:
            logger.debug("通过正则表达式解析到 %d 个阵容", len(comps))
            return comps

        logger.warning("所有解析策略均未能提取阵容数据")
        return None

    def _try_extract_embedded_json(self, soup: BeautifulSoup) -> list[dict[str, Any]] | None:
        """尝试从内嵌 script 标签中提取 JSON 数据。

        常见模式：
        - <script id="__NEXT_DATA__" type="application/json">...</script>
        - <script>window.__INITIAL_STATE__ = {...}</script>
        - <script type="application/ld+json">...</script>
        """
        comps: list[dict[str, Any]] = []

        for script in soup.find_all("script", type="application/json"):
            try:
                data = json.loads(script.string or "")
                extracted = self._extract_comps_from_dict(data)
                if extracted:
                    comps.extend(extracted)
            except (json.JSONDecodeError, TypeError):
                continue

        if comps:
            return comps

        # 尝试 __NEXT_DATA__ / __INITIAL_STATE__ 模式
        for script in soup.find_all("script"):
            if not script.string:
                continue
            text = script.string
            # 匹配 window.__INITIAL_STATE__ = {...} 或类似模式
            state_match = re.search(
                r'(?:window\.)?__(?:NEXT_DATA__|INITIAL_STATE__|NUXT__|DATA__)\s*=\s*(\{.+?\})\s*;?\s*\n',
                text,
                re.DOTALL,
            )
            if not state_match:
                # 尝试更宽松的匹配：查找 JSON 对象赋值
                state_match = re.search(
                    r'(?:window\.)?__(?:NEXT_DATA__|INITIAL_STATE__|NUXT__|DATA__)\s*=\s*(\{.+)', text, re.DOTALL
                )
            if state_match:
                try:
                    data = json.loads(state_match.group(1))
                    extracted = self._extract_comps_from_dict(data)
                    if extracted:
                        comps.extend(extracted)
                except (json.JSONDecodeError, TypeError):
                    continue

        return comps if comps else None

    def _try_parse_html_structure(self, soup: BeautifulSoup) -> list[dict[str, Any]] | None:
        """通过 BeautifulSoup 解析 HTML 结构提取阵容数据。

        尝试常见的阵容列表 HTML 模式：
        - 包含 data-tier, data-name 等属性的卡片元素
        - class 名称包含 "comp", "composition", "team", "meta" 的容器
        """
        comps: list[dict[str, Any]] = []

        # 查找可能的阵容卡片容器
        cards: list[Any] = soup.find_all(attrs={"data-tier": True})
        if not cards:
            cards = soup.find_all(class_=re.compile(r"comp|composition|team|meta.*card", re.I))

        if not cards:
            # 尝试通过常见结构查找
            cards = soup.find_all(["article", "li", "tr"], class_=re.compile(r"comp|team|row", re.I))
        if not cards:
            # 尝试 div 中包含 tier 文本的
            for div in soup.find_all("div"):
                text = div.get_text()
                if re.search(r"[SABCD]\s*(级|级别|tier)", text, re.I):
                    cards.append(div)

        for card in cards:
            try:
                comp = self._parse_card_to_comp(card)
                if comp and self._validate_comp_data(comp):
                    comps.append(comp)
            except Exception:
                continue

        return comps if comps else None

    def _try_regex_extraction(self, html: str) -> list[dict[str, Any]] | None:
        """使用正则表达式从 HTML 文本中提取阵容数据。

        这是最后的兜底策略，仅提取文本中的关键字段：
        阵容名称、tier、胜率、登场率。
        """
        # 去除 HTML 标签，只保留文本
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()

        comps: list[dict[str, Any]] = []

        # 匹配模式: 阵容名 (S/A/B/C级) 胜率:xx% 登场率:xx% 平均排名:x.x
        # 例: "八法师 S级 胜率:18.5% 登场率:5.2% 平均排名:3.2"
        pattern = re.compile(
            r"([一-鿿\w]+)\s*"  # 阵容名称
            r"[SABCD]\s*(?:级|级别|tier)\s*"  # tier
            r".*?"
            r"(?:胜率|win\s*rate)[:：]?\s*([\d.]+)\s*%?\s*"
            r".*?"
            r"(?:登场率|play\s*rate)[:：]?\s*([\d.]+)\s*%?\s*"
            r".*?"
            r"(?:平均排名|avg\s*(?:placement|rank))[:：]?\s*([\d.]+)",
            re.IGNORECASE,
        )

        for match in pattern.finditer(text):
            try:
                name = match.group(1).strip()
                win_rate = float(match.group(2)) / 100.0 if float(match.group(2)) > 1 else float(match.group(2))
                play_rate = float(match.group(3)) / 100.0 if float(match.group(3)) > 1 else float(match.group(3))
                avg_placement = float(match.group(4))

                tier = self._infer_tier_from_position(avg_placement)

                comps.append(
                    {
                        "name": name,
                        "tier": tier,
                        "playstyle": "运营",
                        "avg_placement": avg_placement,
                        "win_rate": win_rate,
                        "play_rate": play_rate,
                        "description": None,
                        "champions": [],
                        "items": [],
                    }
                )
            except (ValueError, IndexError):
                continue

        return comps if comps else None

    # --- 辅助方法 ---

    @staticmethod
    def _extract_comps_from_dict(data: Any) -> list[dict[str, Any]]:
        """递归搜索字典/列表中的阵容数据。"""
        results: list[dict[str, Any]] = []

        if isinstance(data, dict):
            # 检测是否是阵容数据对象
            if "name" in data and ("tier" in data or "avg_placement" in data or "win_rate" in data):
                results.append(data)
            for value in data.values():
                results.extend(TacticsToolsCrawler._extract_comps_from_dict(value))
        elif isinstance(data, list):
            for item in data:
                results.extend(TacticsToolsCrawler._extract_comps_from_dict(item))

        return results

    @staticmethod
    def _parse_card_to_comp(card: Any) -> dict[str, Any] | None:
        """从单个 HTML 卡片元素解析阵容数据。"""
        text = card.get_text(" ", strip=True)

        name = card.get("data-name") or card.get("data-comp-name")
        tier = card.get("data-tier")

        if not name:
            # 尝试从内部元素查找名称
            name_el = card.find(["h2", "h3", "h4", "span", "div"], class_=re.compile(r"name|title", re.I))
            if name_el:
                name = name_el.get_text(strip=True)

        if not name:
            return None

        if not tier:
            tier_match = re.search(r"[SABCD]", text[:20])
            tier = tier_match.group(0) if tier_match else "B"

        # 提取胜率和排名数据
        wr_match = re.search(r"(?:胜率|win\s*rate)[:：\s]*([\d.]+)\s*%?", text, re.I)
        pr_match = re.search(r"(?:登场率|play\s*rate)[:：\s]*([\d.]+)\s*%?", text, re.I)
        ap_match = re.search(r"(?:平均排名|avg\s*(?:placement|rank))[:：\s]*([\d.]+)", text, re.I)

        return {
            "name": name,
            "tier": tier,
            "playstyle": "运营",
            "avg_placement": float(ap_match.group(1)) if ap_match else 4.5,
            "win_rate": _normalize_rate(wr_match.group(1)) if wr_match else 0.0,
            "play_rate": _normalize_rate(pr_match.group(1)) if pr_match else 0.0,
            "description": None,
            "champions": [],
            "items": [],
        }

    @staticmethod
    def _validate_comp_data(comp: dict[str, Any]) -> bool:
        """验证阵容数据是否完整有效。"""
        if not comp.get("name"):
            return False
        tier = comp.get("tier", "")
        if tier and tier.upper() not in ("S", "A", "B", "C", "D"):
            return False
        return True

    @staticmethod
    def _infer_tier_from_position(avg_placement: float) -> str:
        """根据平均排名推断 tier。"""
        if avg_placement <= 3.5:
            return "S"
        elif avg_placement <= 4.0:
            return "A"
        elif avg_placement <= 4.5:
            return "B"
        else:
            return "C"

    @staticmethod
    def _load_champion_map(session: Any) -> dict[str, int]:
        """加载数据库中已有的 champion name → id 映射。"""
        champions = session.query(Champion).all()
        return {c.name: c.id for c in champions}

    @staticmethod
    def _load_item_map(session: Any) -> dict[str, int]:
        """加载数据库中已有的 item name → id 映射。"""
        items = session.query(Item).all()
        return {i.name: i.id for i in items}

    def close(self) -> None:
        """关闭 HTTP 客户端，释放资源。"""
        self._client.close()


def _normalize_rate(raw: str) -> float:
    """将百分比字符串标准化为 0-1 之间的浮点数。"""
    try:
        value = float(raw)
    except ValueError:
        return 0.0
    return value / 100.0 if value > 1 else value
