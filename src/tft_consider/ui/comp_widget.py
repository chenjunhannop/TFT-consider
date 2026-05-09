"""阵容可视化组件。

CompositionWidget 使用 QPainter 绘制 4x7 棋盘站位图，
展示羁绊激活列表、装备合成路径，并支持多阵容切换和拖拽交换棋子位置。
"""

from __future__ import annotations

import json
import logging
from typing import Any, override

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QMouseEvent,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 主题配色常量
# ---------------------------------------------------------------------------

_COLORS_DARK = {
    "bg": QColor("#1a1a2e"),
    "board_bg": QColor("#2a2a4e"),
    "cell_empty": QColor("#1e1e3a"),
    "cell_occupied": QColor("#16213e"),
    "cell_border": QColor("#3a3a6e"),
    "cell_core_border": QColor("#ffd700"),
    "cell_core_glow": QColor(255, 215, 0, 60),
    "text_primary": QColor("#e0e0e0"),
    "text_secondary": QColor("#a0a0b0"),
    "text_dim": QColor("#666680"),
    "star_active": QColor("#ffd700"),
    "star_inactive": QColor("#4a4a6a"),
    "item_bg": QColor("#0f3460"),
    "item_text": QColor("#e0e0e0"),
    "synergy_active": QColor("#4ecca3"),
    "synergy_inactive": QColor("#666680"),
    "synergy_breakpoint": QColor("#a0a0b0"),
    "tab_active": QColor("#e94560"),
    "tab_inactive": QColor("#a0a0b0"),
    "drag_highlight": QColor("#e94560"),
    "match_score_high": QColor("#4ecca3"),
    "match_score_mid": QColor("#ffd700"),
    "match_score_low": QColor("#e94560"),
    "header_bg": QColor("#16213e"),
}

_COLORS_LIGHT = {
    "bg": QColor("#ffffff"),
    "board_bg": QColor("#e8e8e8"),
    "cell_empty": QColor("#f5f5f5"),
    "cell_occupied": QColor("#e0e0e0"),
    "cell_border": QColor("#cccccc"),
    "cell_core_border": QColor("#c8a200"),
    "cell_core_glow": QColor(200, 162, 0, 40),
    "text_primary": QColor("#333333"),
    "text_secondary": QColor("#666666"),
    "text_dim": QColor("#999999"),
    "star_active": QColor("#c8a200"),
    "star_inactive": QColor("#cccccc"),
    "item_bg": QColor("#d0d0d0"),
    "item_text": QColor("#333333"),
    "synergy_active": QColor("#2d8a6e"),
    "synergy_inactive": QColor("#999999"),
    "synergy_breakpoint": QColor("#666666"),
    "tab_active": QColor("#d43850"),
    "tab_inactive": QColor("#666666"),
    "drag_highlight": QColor("#d43850"),
    "match_score_high": QColor("#2d8a6e"),
    "match_score_mid": QColor("#c8a200"),
    "match_score_low": QColor("#d43850"),
    "header_bg": QColor("#e8e8e8"),
}

# 棋盘常量
_ROWS = 4
_COLS = 7
_CELL_SIZE = 48
_BOARD_MARGIN = 4

# 字体
_FONT_FAMILY = "Arial, PingFang SC, Microsoft YaHei, sans-serif"


def _first_char(name: str) -> str:
    """取棋子名称的第一个字，用于缩略显示。"""
    if not name:
        return "?"
    return name[0]


def _star_str(count: int) -> str:
    """将星级数字转换为 ★ 字符串。"""
    return "★" * max(0, min(count, 3))


def _item_abbr(name: str, max_len: int = 2) -> str:
    """装备名称缩写（取前 N 个字）。"""
    if not name:
        return ""
    return name[:max_len]


def _get_colors(theme: str) -> dict[str, QColor]:
    """根据主题名返回配色字典。"""
    return _COLORS_DARK if theme == "dark" else _COLORS_LIGHT


# ---------------------------------------------------------------------------
# BoardCell —— 棋盘格子数据
# ---------------------------------------------------------------------------


class BoardCell:
    """棋盘上单个格子的数据。"""

    __slots__ = (
        "row",
        "col",
        "champion_name",
        "star_target",
        "is_core",
        "items",
        "champion_id",
        "occupied",
    )

    def __init__(
        self,
        row: int,
        col: int,
        champion_name: str = "",
        star_target: int = 1,
        is_core: bool = False,
        items: list[str] | None = None,
        champion_id: int = 0,
    ) -> None:
        self.row = row
        self.col = col
        self.champion_name = champion_name
        self.star_target = star_target
        self.is_core = is_core
        self.items = items or []
        self.champion_id = champion_id
        self.occupied = bool(champion_name)


# ---------------------------------------------------------------------------
# BoardArea —— 棋盘绘制区域（内嵌于 CompositionWidget）
# ---------------------------------------------------------------------------


class BoardArea(QWidget):
    """4x7 棋盘自定义绘制区域，支持鼠标拖拽交换棋子。"""

    # 拖拽状态
    drag_start_cell: tuple[int, int] | None
    drag_current_cell: tuple[int, int] | None

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cells: dict[tuple[int, int], BoardCell] = {}
        self._colors: dict[str, QColor] = _COLORS_DARK
        self._init_cells()
        self.setMouseTracking(True)
        self.drag_start_cell = None
        self.drag_current_cell = None
        self.setMinimumSize(
            _COLS * _CELL_SIZE + _BOARD_MARGIN * 2,
            _ROWS * _CELL_SIZE + _BOARD_MARGIN * 2,
        )

    def _init_cells(self) -> None:
        """初始化所有格子为空。"""
        self._cells.clear()
        for row in range(_ROWS):
            for col in range(_COLS):
                self._cells[(row, col)] = BoardCell(row, col)

    def set_colors(self, colors: dict[str, QColor]) -> None:
        """设置绘制配色。"""
        self._colors = colors
        self.update()

    def clear_board(self) -> None:
        """清空棋盘所有棋子数据。"""
        self._init_cells()
        self.update()

    def place_champion(
        self,
        row: int,
        col: int,
        name: str,
        star_target: int = 2,
        is_core: bool = False,
        items: list[str] | None = None,
        champion_id: int = 0,
    ) -> None:
        """在指定位置放置棋子。"""
        if 0 <= row < _ROWS and 0 <= col < _COLS:
            self._cells[(row, col)] = BoardCell(
                row=row,
                col=col,
                champion_name=name,
                star_target=star_target,
                is_core=is_core,
                items=items or [],
                champion_id=champion_id,
            )
            self.update()

    def get_cell(self, row: int, col: int) -> BoardCell | None:
        """获取指定位置的格子。"""
        return self._cells.get((row, col))

    def get_all_occupied(self) -> list[BoardCell]:
        """返回所有有棋子的格子。"""
        return [c for c in self._cells.values() if c.occupied]

    @staticmethod
    def _cell_rect(row: int, col: int) -> QRect:
        """返回指定格子的像素矩形。"""
        x = _BOARD_MARGIN + col * _CELL_SIZE
        y = _BOARD_MARGIN + row * _CELL_SIZE
        return QRect(x, y, _CELL_SIZE, _CELL_SIZE)

    def _hit_test(self, pos: QPoint) -> tuple[int, int] | None:
        """像素坐标 → (row, col)，未命中返回 None。"""
        for row in range(_ROWS):
            for col in range(_COLS):
                if self._cell_rect(row, col).contains(pos):
                    return (row, col)
        return None

    # ------------------------------------------------------------------
    # 绘制
    # ------------------------------------------------------------------

    @staticmethod
    def _small_font() -> QFont:
        font = QFont(_FONT_FAMILY, 7)
        return font

    @staticmethod
    def _champ_font() -> QFont:
        font = QFont(_FONT_FAMILY, 13)
        font.setBold(True)
        return font

    @staticmethod
    def _star_font() -> QFont:
        return QFont(_FONT_FAMILY, 8)

    @override
    def paintEvent(self, event: Any) -> None:  # noqa: ARG002
        """绘制 4x7 棋盘。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        colors = self._colors
        total_w = _COLS * _CELL_SIZE + _BOARD_MARGIN * 2
        total_h = _ROWS * _CELL_SIZE + _BOARD_MARGIN * 2

        # 棋盘背景
        painter.fillRect(0, 0, total_w, total_h, colors["board_bg"])

        # 绘制每个格子
        for row in range(_ROWS):
            for col in range(_COLS):
                cell = self._cells.get((row, col))
                self._draw_cell(painter, row, col, cell, colors)

        # 绘制拖拽高亮
        if self.drag_current_cell is not None:
            r, c = self.drag_current_cell
            rect = self._cell_rect(r, c)
            pen = QPen(colors["drag_highlight"], 2)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect.adjusted(1, 1, -1, -1))

        painter.end()

    def _draw_cell(
        self,
        painter: QPainter,
        row: int,
        col: int,
        cell: BoardCell | None,
        colors: dict[str, QColor],
    ) -> None:
        """绘制单个棋盘格子。"""
        rect = self._cell_rect(row, col)
        inner = rect.adjusted(2, 2, -2, -2)

        if cell is not None and cell.occupied:
            # 核心棋子发光效果
            if cell.is_core:
                glow_rect = rect.adjusted(0, 0, 0, 0)
                painter.fillRect(glow_rect, colors["cell_core_glow"])

            # 格子背景
            painter.fillRect(inner, colors["cell_occupied"])

            # 边框（核心金色，普通灰色）
            border_color = colors["cell_core_border"] if cell.is_core else colors["cell_border"]
            border_width = 2 if cell.is_core else 1
            pen = QPen(border_color, border_width)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(inner)

            # 棋子名称首字（居中靠上）
            painter.setPen(colors["text_primary"])
            painter.setFont(self._champ_font())
            fm = QFontMetrics(self._champ_font())
            name_text = _first_char(cell.champion_name)
            name_x = inner.center().x() - fm.horizontalAdvance(name_text) // 2
            name_y = inner.top() + 16
            painter.drawText(name_x, name_y, name_text)

            # 星级
            painter.setPen(colors["star_active"])
            painter.setFont(self._star_font())
            s_text = _star_str(cell.star_target)
            star_x = inner.center().x() - len(s_text) * 5
            star_y = inner.top() + 28
            painter.drawText(star_x, star_y, s_text)

            # 装备（格子底部小字）
            if cell.items:
                painter.setFont(self._small_font())
                item_text = " ".join(_item_abbr(it) for it in cell.items[:3])
                painter.setPen(colors["item_text"])
                painter.fillRect(
                    QRect(inner.left() + 2, inner.bottom() - 14, inner.width() - 4, 12),
                    colors["item_bg"],
                )
                align_flag = Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter
                painter.drawText(inner.adjusted(2, 0, -2, -2), align_flag, item_text)
        else:
            # 空格子
            painter.fillRect(inner, colors["cell_empty"])
            pen = QPen(colors["cell_border"], 1)
            pen.setStyle(Qt.PenStyle.DotLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(inner)

    # ------------------------------------------------------------------
    # 鼠标拖拽
    # ------------------------------------------------------------------

    @override
    def mousePressEvent(self, event: QMouseEvent) -> None:
        """鼠标按下：检测是否点击了有棋子的格子。"""
        if event.button() == Qt.MouseButton.LeftButton:
            hit = self._hit_test(event.pos())
            if hit is not None:
                cell = self._cells.get(hit)
                if cell is not None and cell.occupied:
                    self.drag_start_cell = hit
                    self.drag_current_cell = hit
                    self.setCursor(Qt.CursorShape.ClosedHandCursor)
                    self.update()
                    return
        super().mousePressEvent(event)

    @override
    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """鼠标移动：更新拖拽高亮位置。"""
        if self.drag_start_cell is not None:
            hit = self._hit_test(event.pos())
            self.drag_current_cell = hit
            self.update()
            return
        super().mouseMoveEvent(event)

    @override
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """鼠标释放：完成拖拽交换。"""
        if self.drag_start_cell is not None:
            hit = self._hit_test(event.pos())
            if hit is not None and hit != self.drag_start_cell:
                # 交换两个格子的数据
                src = self._cells[self.drag_start_cell]
                dst = self._cells[hit]
                self._cells[self.drag_start_cell] = BoardCell(
                    row=src.row,
                    col=src.col,
                    champion_name=dst.champion_name,
                    star_target=dst.star_target,
                    is_core=dst.is_core,
                    items=list(dst.items),
                    champion_id=dst.champion_id,
                )
                self._cells[hit] = BoardCell(
                    row=dst.row,
                    col=dst.col,
                    champion_name=src.champion_name,
                    star_target=src.star_target,
                    is_core=src.is_core,
                    items=list(src.items),
                    champion_id=src.champion_id,
                )
                logger.debug("棋子交换: (%d,%d) <-> (%d,%d)", *self.drag_start_cell, *hit)

            self.drag_start_cell = None
            self.drag_current_cell = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.update()
            return
        super().mouseReleaseEvent(event)

    @override
    def sizeHint(self) -> Any:
        """建议尺寸。"""
        from PySide6.QtCore import QSize
        return QSize(
            _COLS * _CELL_SIZE + _BOARD_MARGIN * 2,
            _ROWS * _CELL_SIZE + _BOARD_MARGIN * 2,
        )


# ---------------------------------------------------------------------------
# CompositionWidget
# ---------------------------------------------------------------------------


class CompositionWidget(QWidget):
    """阵容可视化组件。

    包含：多阵容切换 TabBar、4x7 棋盘站位图、羁绊激活列表、装备合成路径。
    """

    # 信号：当前展示的阵容切换时发出
    composition_changed = Signal(int)  # composition_id

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._compositions: list[dict[str, Any]] = []
        self._current_index: int = -1
        self._game_state: dict[str, Any] | None = None
        self._theme: str = "dark"
        self._colors: dict[str, QColor] = _COLORS_DARK

        self._setup_ui()
        self._show_placeholder("暂无阵容数据")

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        """构建组件布局：Tab 切换 + 棋盘 + 羁绊 + 装备。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # -- 阵容切换 TabBar --
        self._tab_bar = QTabBar()
        self._tab_bar.setExpanding(False)
        self._tab_bar.setDrawBase(False)
        self._tab_bar.setElideMode(Qt.TextElideMode.ElideRight)
        self._tab_bar.currentChanged.connect(self._on_tab_changed)
        self._tab_bar.hide()
        layout.addWidget(self._tab_bar)

        # -- 滚动区域（棋盘 + 详细信息） --
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._inner = QWidget()
        inner_layout = QVBoxLayout(self._inner)
        inner_layout.setContentsMargins(4, 2, 4, 2)
        inner_layout.setSpacing(4)

        # 棋盘标题
        self._board_title = QLabel("棋盘站位")
        self._board_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        inner_layout.addWidget(self._board_title)

        # 棋盘绘制区
        self._board = BoardArea()
        self._board_container = QWidget()
        board_container_layout = QHBoxLayout(self._board_container)
        board_container_layout.setContentsMargins(0, 0, 0, 0)
        board_container_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        board_container_layout.addWidget(self._board)
        inner_layout.addWidget(self._board_container)

        # 羁绊区域
        self._synergy_title = QLabel("羁绊")
        self._synergy_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        inner_layout.addWidget(self._synergy_title)
        self._synergy_label = QLabel("")
        self._synergy_label.setWordWrap(True)
        self._synergy_label.setTextFormat(Qt.TextFormat.RichText)
        inner_layout.addWidget(self._synergy_label)

        # 装备区域
        self._item_title = QLabel("推荐装备")
        self._item_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        inner_layout.addWidget(self._item_title)
        self._item_label = QLabel("")
        self._item_label.setWordWrap(True)
        self._item_label.setTextFormat(Qt.TextFormat.RichText)
        inner_layout.addWidget(self._item_label)

        inner_layout.addStretch()

        self._scroll_area.setWidget(self._inner)
        layout.addWidget(self._scroll_area)

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def set_composition(self, comp: dict[str, Any]) -> None:
        """设置要展示的单个阵容。

        Args:
            comp: 单个阵容字典，来自 match_compositions() 返回的元素。
        """
        self.set_compositions([comp], None)

    def set_compositions(
        self,
        comps: list[dict[str, Any]],
        game_state: dict[str, Any] | None = None,
    ) -> None:
        """设置多个阵容并支持切换。

        Args:
            comps: 阵容字典列表。
            game_state: 当前游戏状态（可选，用于高亮已持有棋子）。
        """
        self._compositions = comps
        self._game_state = game_state

        if not comps:
            self._current_index = -1
            self._tab_bar.hide()
            self._show_placeholder("暂无阵容数据")
            return

        # 更新 TabBar
        self._tab_bar.blockSignals(True)
        while self._tab_bar.count() > 0:
            self._tab_bar.removeTab(0)
        for i, comp in enumerate(comps):
            name = comp.get("name", f"阵容{i + 1}")
            tier = comp.get("tier", "?")
            score = comp.get("match_score", 0)
            label = f"[{tier}] {name} ({score}分)"
            self._tab_bar.addTab(label)
        self._tab_bar.blockSignals(False)

        if len(comps) > 1:
            self._tab_bar.show()
        else:
            self._tab_bar.hide()

        # 显示第一个阵容
        self._current_index = 0
        self._tab_bar.setCurrentIndex(0)
        self._render_composition(0)

    # ------------------------------------------------------------------
    # 主题
    # ------------------------------------------------------------------

    def set_theme(self, theme: str) -> None:
        """设置深浅色主题。

        Args:
            theme: "dark" 或 "light"。
        """
        self._theme = theme
        self._colors = _get_colors(theme)
        self._board.set_colors(self._colors)
        self._apply_theme_styles()
        if self._current_index >= 0:
            self._render_composition(self._current_index)

    # ------------------------------------------------------------------
    # 内部：阵容渲染
    # ------------------------------------------------------------------

    def _on_tab_changed(self, index: int) -> None:
        """Tab 切换回调。"""
        if 0 <= index < len(self._compositions):
            self._current_index = index
            self._render_composition(index)
            comp_id = self._compositions[index].get("composition_id", 0)
            self.composition_changed.emit(comp_id)

    def _apply_theme_styles(self) -> None:
        """应用主题样式到标签控件。"""
        c = self._colors
        text_style = f"color: {c['text_primary'].name()}; font-size: 11px;"
        title_style = f"color: {c['text_secondary'].name()}; font-size: 10px; font-weight: bold; padding-top: 4px;"

        self._board_title.setStyleSheet(title_style)
        self._synergy_title.setStyleSheet(title_style)
        self._item_title.setStyleSheet(title_style)
        self._synergy_label.setStyleSheet(text_style)
        self._item_label.setStyleSheet(text_style)

        # Tab bar 样式
        if self._theme == "dark":
            self._tab_bar.setStyleSheet("""
                QTabBar::tab {
                    background: #16213e;
                    color: #a0a0b0;
                    padding: 4px 10px;
                    border: 1px solid #0f3460;
                    border-bottom: none;
                    font-size: 11px;
                    min-width: 60px;
                }
                QTabBar::tab:selected {
                    background: #0f3460;
                    color: #e94560;
                    font-weight: bold;
                }
                QTabBar::tab:hover:!selected {
                    color: #e0e0e0;
                }
            """)
        else:
            self._tab_bar.setStyleSheet("""
                QTabBar::tab {
                    background: #e0e0e0;
                    color: #666666;
                    padding: 4px 10px;
                    border: 1px solid #cccccc;
                    border-bottom: none;
                    font-size: 11px;
                    min-width: 60px;
                }
                QTabBar::tab:selected {
                    background: #ffffff;
                    color: #d43850;
                    font-weight: bold;
                }
                QTabBar::tab:hover:!selected {
                    color: #333333;
                }
            """)

    def _render_composition(self, index: int) -> None:
        """渲染指定索引的阵容数据到棋盘、羁绊和装备区域。"""
        if index < 0 or index >= len(self._compositions):
            return
        comp = self._compositions[index]
        self._apply_theme_styles()

        # 1. 棋盘站位
        self._board.clear_board()
        self._place_champions_on_board(comp)

        # 2. 羁绊
        self._render_synergies(comp)

        # 3. 装备
        self._render_items(comp)

    def _place_champions_on_board(self, comp: dict[str, Any]) -> None:
        """将阵容棋子放置到棋盘上。"""
        composition_id = comp.get("composition_id", 0)
        positioning = comp.get("positioning")

        # 尝试从数据库获取详细棋子信息
        db_champs: dict[int, dict[str, Any]] = {}
        db_positions: dict[int, str] = {}
        try:
            db_champs, db_positions = self._query_comp_champions(composition_id)
        except Exception:
            logger.debug("无法查询数据库中的棋子信息", exc_info=True)

        # 合并 positioning 数据（优先使用数据库中的 position 字段）
        if positioning and isinstance(positioning, list):
            for entry in positioning:
                if not isinstance(entry, dict):
                    continue
                name = str(entry.get("champion", ""))
                row = int(entry.get("row", 0))
                col = int(entry.get("col", 0))
                if name and 0 <= row < _ROWS and 0 <= col < _COLS:
                    self._board.place_champion(
                        row=row,
                        col=col,
                        name=name,
                        star_target=2,
                        is_core=bool(entry.get("is_core", False)),
                    )
            return

        # 如果 positioning 为空，使用数据库 position 或自动排列
        if db_champs:
            occupied_positions: set[tuple[int, int]] = set()
            # 先放有明确 position 的棋子
            for cid, info in db_champs.items():
                pos = db_positions.get(cid, "")
                if pos:
                    try:
                        parts = pos.split(",")
                        row = int(parts[0].strip())
                        col = int(parts[1].strip())
                        if 0 <= row < _ROWS and 0 <= col < _COLS and (row, col) not in occupied_positions:
                            self._board.place_champion(
                                row=row, col=col,
                                name=info["name"],
                                star_target=info.get("star_target", 2),
                                is_core=info.get("is_core", False),
                                champion_id=cid,
                            )
                            occupied_positions.add((row, col))
                            continue
                    except (ValueError, IndexError):
                        pass

            # 剩余棋子自动排列
            auto_index = 0
            for cid, info in db_champs.items():
                existing_pos = db_positions.get(cid, "")
                if existing_pos:
                    continue  # 已放置
                while auto_index < _ROWS * _COLS:
                    row = auto_index // _COLS
                    col = auto_index % _COLS
                    auto_index += 1
                    if (row, col) not in occupied_positions:
                        self._board.place_champion(
                            row=row, col=col,
                            name=info["name"],
                            star_target=info.get("star_target", 2),
                            is_core=info.get("is_core", False),
                            champion_id=cid,
                        )
                        occupied_positions.add((row, col))
                        break
            return

        # 兜底：显示空棋盘 + 提示
        logger.debug("无 positioning 数据且数据库无棋子信息，棋盘留空")

    def _render_synergies(self, comp: dict[str, Any]) -> None:
        """渲染羁绊激活列表（RichText HTML）。"""
        composition_id = comp.get("composition_id", 0)
        colors = self._colors

        try:
            synergies = self._query_synergies(composition_id)
        except Exception:
            logger.debug("查询羁绊失败", exc_info=True)
            dim_color = colors["text_dim"].name()
            self._synergy_label.setText(
                f"<span style='color:{dim_color}'>无法加载羁绊数据</span>"
            )
            return

        if not synergies:
            dim_color = colors["text_dim"].name()
            self._synergy_label.setText(
                f"<span style='color:{dim_color}'>无羁绊数据</span>"
            )
            return

        # 统计每个羁绊的当前棋子数
        trait_counts: dict[str, int] = {}
        occupied = self._board.get_all_occupied()
        occupied_names = {c.champion_name for c in occupied}

        # 查询棋子-羁绊映射来统计
        try:
            trait_counts = self._query_trait_counts(composition_id, occupied_names)
        except Exception:
            logger.debug("查询羁绊计数失败", exc_info=True)

        parts: list[str] = []
        for syn in synergies:
            name = syn.get("name", "?")
            breakpoints = syn.get("breakpoints", [])
            count = trait_counts.get(name, 0)

            # 检查是否激活了某个断点
            activated_bp = 0
            if isinstance(breakpoints, list):
                for bp in sorted(breakpoints):
                    if count >= bp:
                        activated_bp = bp

            is_active = activated_bp > 0
            active_color = colors["synergy_active"].name()
            inactive_color = colors["synergy_inactive"].name()

            color = active_color if is_active else inactive_color

            # 断点显示: 高亮已激活的断点
            bp_parts = []
            if isinstance(breakpoints, list):
                for bp in breakpoints:
                    if count >= bp:
                        bp_parts.append(f"<b>{bp}</b>")
                    else:
                        bp_parts.append(str(bp))

            bp_text = "/".join(bp_parts)
            line = (
                f"<span style='color:{color}'>"
                f"{name} ({count}) [{bp_text}]"
                f"</span>"
            )
            parts.append(line)

        separator = f"<span style='color:{colors['text_dim'].name()}'>  |  </span>"
        self._synergy_label.setText(separator.join(parts))

    def _render_items(self, comp: dict[str, Any]) -> None:
        """渲染推荐装备列表（RichText HTML），含合成路径。"""
        composition_id = comp.get("composition_id", 0)
        colors = self._colors

        try:
            items = self._query_comp_items(composition_id)
        except Exception:
            logger.debug("查询装备失败", exc_info=True)
            dim_color = colors["text_dim"].name()
            self._item_label.setText(
                f"<span style='color:{dim_color}'>无法加载装备数据</span>"
            )
            return

        if not items:
            dim_color = colors["text_dim"].name()
            self._item_label.setText(
                f"<span style='color:{dim_color}'>无推荐装备</span>"
            )
            return

        parts: list[str] = []
        for item in items:
            name = item.get("name", "?")
            components = item.get("components", [])
            champion = item.get("champion_name", "")
            priority = item.get("priority", 1)

            priority_mark = "★" if priority == 1 else ""

            if isinstance(components, list) and components:
                comp_text = " + ".join(str(c) for c in components)
                line = (
                    f"<span style='color:{colors['text_primary'].name()}'>{priority_mark}{name}</span>"
                    f"<span style='color:{colors['text_dim'].name()}'> ← {comp_text}</span>"
                )
            else:
                line = f"<span style='color:{colors['text_primary'].name()}'>{priority_mark}{name}</span>"

            if champion:
                line += (
                    f" <span style='color:{colors['synergy_active'].name()}; font-size:10px;'>"
                    f"[{_first_char(champion)}]</span>"
                )

            parts.append(line)

        self._item_label.setText("<br>".join(parts))

    # ------------------------------------------------------------------
    # 数据库查询
    # ------------------------------------------------------------------

    @staticmethod
    def _query_comp_champions(
        composition_id: int,
    ) -> tuple[dict[int, dict[str, Any]], dict[int, str]]:
        """查询阵容中所有棋子的详细信息。

        Returns:
            (champion_map, position_map)
            champion_map: {champion_id: {name, star_target, is_core, ...}}
            position_map: {champion_id: "row,col"}
        """
        from tft_consider.database.models import Champion, CompChampion, get_session

        session = get_session()
        try:
            rows = (
                session.query(CompChampion, Champion)
                .join(Champion, CompChampion.champion_id == Champion.id)
                .filter(CompChampion.composition_id == composition_id)
                .all()
            )
            champ_map: dict[int, dict[str, Any]] = {}
            pos_map: dict[int, str] = {}
            for cc, champ in rows:
                champ_map[cc.champion_id] = {
                    "name": champ.name,
                    "star_target": cc.star_target,
                    "is_core": cc.is_core,
                    "cost": champ.cost,
                    "traits": champ.traits,
                }
                if cc.position:
                    pos_map[cc.champion_id] = cc.position
            return champ_map, pos_map
        finally:
            session.close()

    @staticmethod
    def _query_synergies(composition_id: int) -> list[dict[str, Any]]:
        """查询阵容涉及的羁绊详情。

        通过 棋子.traits (JSON list) → Synergy 表匹配。

        Returns:
            [{name, breakpoints, effect_per_level}, ...]
        """
        from tft_consider.database.models import Champion, CompChampion, Synergy, get_session

        session = get_session()
        try:
            # 获取该阵容所有棋子的 traits
            rows = (
                session.query(Champion.traits)
                .join(CompChampion, CompChampion.champion_id == Champion.id)
                .filter(CompChampion.composition_id == composition_id)
                .all()
            )

            all_trait_names: set[str] = set()
            for (traits_json,) in rows:
                if traits_json:
                    try:
                        traits = json.loads(traits_json)
                        if isinstance(traits, list):
                            for t in traits:
                                if isinstance(t, str):
                                    all_trait_names.add(t)
                    except (json.JSONDecodeError, TypeError):
                        pass

            if not all_trait_names:
                return []

            # 查询对应的 Synergy 记录
            synergies = (
                session.query(Synergy)
                .filter(Synergy.name.in_(all_trait_names))
                .all()
            )

            result: list[dict[str, Any]] = []
            for syn in synergies:
                breakpoints = []
                if syn.breakpoints:
                    try:
                        breakpoints = json.loads(syn.breakpoints)
                    except (json.JSONDecodeError, TypeError):
                        breakpoints = []
                result.append({
                    "name": syn.name,
                    "breakpoints": breakpoints if isinstance(breakpoints, list) else [],
                    "effect_per_level": syn.effect_per_level,
                })
            return result
        finally:
            session.close()

    @staticmethod
    def _query_trait_counts(
        composition_id: int,
        occupied_names: set[str],
    ) -> dict[str, int]:
        """统计当前棋盘上各羁绊的棋子数。

        Args:
            composition_id: 阵容 ID。
            occupied_names: 当前棋盘上的棋子名称集合。

        Returns:
            {trait_name: count}
        """
        from tft_consider.database.models import Champion, CompChampion, get_session

        session = get_session()
        try:
            rows = (
                session.query(Champion.name, Champion.traits)
                .join(CompChampion, CompChampion.champion_id == Champion.id)
                .filter(CompChampion.composition_id == composition_id)
                .all()
            )

            counts: dict[str, int] = {}
            for champ_name, traits_json in rows:
                if champ_name in occupied_names and traits_json:
                    try:
                        traits = json.loads(traits_json)
                        if isinstance(traits, list):
                            for t in traits:
                                if isinstance(t, str):
                                    counts[t] = counts.get(t, 0) + 1
                    except (json.JSONDecodeError, TypeError):
                        pass
            return counts
        finally:
            session.close()

    @staticmethod
    def _query_comp_items(composition_id: int) -> list[dict[str, Any]]:
        """查询阵容的推荐装备及合成配方。

        Returns:
            [{name, components, champion_name, priority}, ...]
        """
        from tft_consider.database.models import Champion, CompItem, Item, get_session

        session = get_session()
        try:
            rows = (
                session.query(CompItem, Item, Champion.name)
                .join(Item, CompItem.item_id == Item.id)
                .outerjoin(Champion, CompItem.champion_id == Champion.id)
                .filter(CompItem.composition_id == composition_id)
                .order_by(CompItem.priority)
                .all()
            )

            result: list[dict[str, Any]] = []
            for ci, item, champ_name in rows:
                components = []
                if item.components:
                    try:
                        components = json.loads(item.components)
                    except (json.JSONDecodeError, TypeError):
                        components = []
                result.append({
                    "name": item.name,
                    "components": components if isinstance(components, list) else [],
                    "champion_name": champ_name or "",
                    "priority": ci.priority,
                })
            return result
        finally:
            session.close()

    # ------------------------------------------------------------------
    # 占位提示
    # ------------------------------------------------------------------

    def _show_placeholder(self, message: str) -> None:
        """显示无数据占位提示。"""
        self._board.clear_board()
        self._synergy_label.setText(
            f"<span style='color:{self._colors['text_dim'].name()}'>{message}</span>"
        )
        self._item_label.setText("")

    # ------------------------------------------------------------------
    # 尺寸提示
    # ------------------------------------------------------------------

    @override
    def minimumSizeHint(self) -> Any:
        """最小尺寸提示。"""
        from PySide6.QtCore import QSize
        return QSize(140, 200)

    @override
    def sizeHint(self) -> Any:
        """建议尺寸。"""
        from PySide6.QtCore import QSize
        return QSize(200, 500)
