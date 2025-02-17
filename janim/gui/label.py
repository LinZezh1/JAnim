from __future__ import annotations

import os
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QFont, QPainter, QPixmap

from janim.anims.animation import TimeRange
from janim.utils.file_ops import get_janim_dir

LABEL_DEFAULT_HEIGHT = 3
LABEL_PIXEL_HEIGHT_PER_UNIT = 8     # px


@dataclass
class PixelRange:
    left: float
    width: float

    @property
    def right(self) -> float:
        return self.left + self.width


class Label:
    def __init__(
        self,
        name: str,
        t_range: TimeRange,
        *,
        pen=Qt.PenStyle.NoPen,
        brush=Qt.BrushStyle.NoBrush,
        font: QFont | None = None
    ):
        self.parent: LabelGroup | None = None
        self.name = name
        self.t_range = t_range
        self.pen = pen
        self.brush = brush
        self.font = font

        self._y: int = 0
        self._height: int = LABEL_DEFAULT_HEIGHT

        # ups 表示该 Label 的顶上还有哪些 Label（y 更小且时间区段存在重叠的其它 Label）
        # downs 表示该 Label 的底下还有哪些 Label（y 更大且时间区段存在重叠的其它 Label）
        self.ups: list[Label] = []
        self.downs: list[Label] = []

        self._needs_refresh_y: bool = True

    # region property

    @property
    def y(self) -> int:
        if not self._needs_refresh_y:
            return self._y

        if self.ups:
            self._y = max(label.y + label.height for label in self.ups)
        else:
            self._y = 0
        self._needs_refresh_y = False
        return self._y

    @property
    def height(self) -> int:
        return self._height

    def mark_needs_refresh_y(self) -> None:
        self._needs_refresh_y = True
        for other in self.downs:
            other.mark_needs_refresh_y()
        if self.parent:
            self.parent.mark_needs_refresh_height()

    # endregion

    # region paint

    @dataclass
    class PaintParams:
        rect: QRect
        range: TimeRange
        y_pixel_offset: float

    @staticmethod
    def time_range_to_pixel_range(params: PaintParams, t_range: TimeRange) -> PixelRange:
        left = params.rect.left() + (t_range.at - params.range.at) / params.range.duration * params.rect.width()
        width = t_range.duration / params.range.duration * params.rect.width()
        return PixelRange(left, width)

    def _paint(
        self,
        p: QPainter,
        params: PaintParams,
        y_offset: int,
        height: int,
        *,
        post_fn: Callable[[QRectF]] | None = None   # 只是为了在 LabelGroup._paint 中绘制 tip 使用
    ) -> None:
        range = self.time_range_to_pixel_range(params, self.t_range)
        y_pixel = params.rect.y() + (self.y + y_offset) * LABEL_PIXEL_HEIGHT_PER_UNIT - params.y_pixel_offset
        rect = QRectF(range.left, y_pixel, range.width, LABEL_PIXEL_HEIGHT_PER_UNIT * height)

        # 标记是否应当绘制文字
        out_of_boundary = False

        # 使得超出底端的区段也能看到一条边
        maximum = params.rect.bottom() - 3  # 本来应该是 -4，但因为 bottom 的特性所以要再 +1
        if rect.y() > maximum:
            rect.moveTop(maximum)
            rect.setHeight(4)
            out_of_boundary = True

        # 使得超出顶端的区段也能看到一条边
        minimum = params.rect.top() + 3     # 本来应该是 +4，但因为 rect.bottom() 的特性所以要再 -1
        if rect.bottom() < minimum:
            rect.setHeight(4)
            rect.moveBottom(minimum)
            out_of_boundary = True

        # 这里的判断使得区段过窄时也能看得见
        if rect.width() > 5:
            x_adjust = 2
        elif rect.width() > 1:
            x_adjust = (rect.width() - 1) / 2
        else:
            x_adjust = 0

        # 绘制背景部分
        if not out_of_boundary:
            rect.adjust(x_adjust, 2, -x_adjust, -2)
        p.setPen(self.pen)
        p.setBrush(self.brush)
        p.drawRect(rect)

        # 使得在区段的左侧有一部分在显示区域外时，
        # 文字仍然对齐到屏幕的左端，而不是跑到屏幕外面去
        if rect.x() < 0:
            rect.setX(0)

        # 绘制文字
        if not out_of_boundary:
            if post_fn is not None:
                post_fn(p, rect)
            rect.adjust(1, 1, -1, -1)
            if self.font is not None:
                prev_font = p.font()
                p.setFont(self.font)
            p.setPen(Qt.GlobalColor.black)
            p.drawText(
                rect,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                self.name
            )
            if self.font is not None:
                p.setFont(prev_font)

    def paint(self, p: QPainter, params: PaintParams, y_offset: int) -> None:
        self._paint(p, params, y_offset, self.height)

    def paint_thumb(self, p: QPainter, params: PaintParams, y_offset: int) -> None:
        pass

    # endregion


class LabelGroup(Label):
    header_height = 2

    def __init__(
        self,
        name: str,
        t_range: TimeRange,
        *labels: Label,
        collapse: bool,
        header: bool,
        pen=Qt.PenStyle.NoPen,
        brush=Qt.BrushStyle.NoBrush,
        font: QFont | None = None,
        highlight_pen=Qt.PenStyle.NoPen,
        highlight_brush=Qt.BrushStyle.NoBrush
    ):
        super().__init__(name, t_range, pen=pen, brush=brush, font=font)
        self.highlight_pen = highlight_pen
        self.highlight_brush = highlight_brush

        self.pix_collapse_tip1 = self.get_pix_collapse_tip1()
        self.pix_collapse_tip2 = self.get_pix_collapse_tip2()

        # 用于优化绘制的遍历
        self.ordered_divisions: list[list[Label]] | None = None
        if len(labels) > 32:   # 该 LabelGroup 中 labels 多于 32 个才进行该优化
            self.ordered_divisions = []

        labels = sorted(labels, key=lambda x: x.t_range.at)
        stack: list[Label | None] = []

        for label in labels:
            label.parent = self

            found_place: bool = False
            max_len = 0
            # if-else 地狱 ¯\_(ツ)_/¯
            for i, other in enumerate(stack):
                if other.t_range.end <= label.t_range.at:
                    if not found_place:
                        if self.ordered_divisions is not None:
                            self.ordered_divisions[i].append(label)
                        stack[i] = label
                        max_len = i + 1
                        found_place = True
                else:
                    max_len = i + 1
                    if found_place:
                        other.ups.append(label)
                        label.downs.append(other)
                    else:
                        label.ups.append(other)
                        other.downs.append(label)

            if found_place:
                if max_len != len(stack):
                    stack = stack[:max_len]
            else:
                if self.ordered_divisions is not None:
                    if len(stack) == len(self.ordered_divisions):
                        self.ordered_divisions.append([label])
                    else:
                        self.ordered_divisions[len(stack)].append(label)
                stack.append(label)

        self.labels = labels
        self._height = 0
        self._collapse = collapse
        self._header = header

        self._needs_refresh_height: bool = True

    # region property

    @property
    def height(self) -> int:
        if not self._needs_refresh_height:
            return self._height

        if self._collapse or not self.labels:
            self._height = 0
        else:
            self._height = max(label.y + label.height for label in self.labels)

        if self._header:
            self._height += self.header_height

        self._needs_refresh_height = False
        return self._height

    def switch_collapse(self) -> None:
        self._collapse = not self._collapse
        self.mark_needs_refresh_height()

    def mark_needs_refresh_height(self) -> None:
        self._needs_refresh_height = True
        for other in self.downs:
            other.mark_needs_refresh_y()
        if self.parent:
            self.parent.mark_needs_refresh_height()

    # endregion

    # region query

    class QueryPolicy(Enum):
        All = 0
        GroupOnly = 1
        HeaderOnly = 2

    def query_at(
        self,
        rect: QRect,
        display_range: TimeRange,
        pos: QPointF,
        y_pixel_offset: float,
        policy: QueryPolicy
    ) -> Label | LabelGroup | None:
        t = (pos.x() - rect.left()) / rect.width() * display_range.duration + display_range.at
        y = (pos.y() - rect.top() + y_pixel_offset) // LABEL_PIXEL_HEIGHT_PER_UNIT
        return self._query_at(t, y, policy)

    def _query_at(self, t: float, y: int, policy: QueryPolicy) -> Label | LabelGroup | None:
        if self._header:
            y -= self.header_height

        if self.ordered_divisions is not None:
            for division in self.ordered_divisions:
                left = bisect_left(division, t, key=lambda x: x.t_range.at)
                left = max(0, left - 1)
                right = bisect_right(division, t, key=lambda x: x.t_range.end)
                right = min(len(division), right + 1)
                for i in range(left, right):
                    label = division[i]
                    result = self._query_label(label, t, y - label.y, policy)
                    if result is not None:
                        return result
        else:
            for label in self.labels:
                result = self._query_label(label, t, y - label.y, policy)
                if result is not None:
                    return result

        return None

    def _query_label(self, label: Label, t: float, y: int, policy: QueryPolicy) -> Label | LabelGroup | None:
        if not label.t_range.at <= t < label.t_range.end:
            return None

        match policy:
            case LabelGroup.QueryPolicy.All:
                if not 0 <= y < label.height:
                    return None

                if isinstance(label, LabelGroup):
                    return label._query_at(t, y, policy) or label
                else:
                    return label

            case LabelGroup.QueryPolicy.GroupOnly:
                if not 0 <= y < label.height:
                    return None
                if not isinstance(label, LabelGroup):
                    return None
                return label._query_at(t, y, policy) or label

            case LabelGroup.QueryPolicy.HeaderOnly:
                if not 0 <= y < label.height:
                    return None
                if not isinstance(label, LabelGroup):
                    return None

                if label._header and 0 <= y < label.header_height:
                    return label
                else:
                    return label._query_at(t, y, policy)

    # endregion

    # region paint

    _pix_collapse_tip1 = None

    @staticmethod
    def get_pix_collapse_tip1() -> QPixmap:
        if LabelGroup._pix_collapse_tip1 is None:
            LabelGroup._pix_collapse_tip1 = QPixmap(os.path.join(get_janim_dir(), 'gui', 'collapse_tip1.png'))
        return LabelGroup._pix_collapse_tip1

    _pix_collapse_tip2 = None

    @staticmethod
    def get_pix_collapse_tip2() -> QPixmap:
        if LabelGroup._pix_collapse_tip2 is None:
            LabelGroup._pix_collapse_tip2 = QPixmap(os.path.join(get_janim_dir(), 'gui', 'collapse_tip2.png'))
        return LabelGroup._pix_collapse_tip2

    def paint(self, p: QPainter, params: Label.PaintParams, y_offset: int = 0) -> None:
        if not self._collapse:
            # 绘制子 Label
            children_offset = y_offset + self.y
            if self._header:
                children_offset += self.header_height

            if self.ordered_divisions is None:
                for label in self.labels:
                    label.paint(p, params, children_offset)
            else:
                for division in self.ordered_divisions:
                    left = bisect_left(division, params.range.at, key=lambda x: x.t_range.at)
                    left = max(0, left - 1)
                    right = bisect_right(division, params.range.end, key=lambda x: x.t_range.end)
                    right = min(len(division), right + 1)
                    for i in range(left, right):
                        division[i].paint(p, params, children_offset)

        # 绘制标题区
        if self._header:
            self._paint(p, params, y_offset, self.header_height, post_fn=self._paint_tip)

    def _paint_tip(self, p: QPainter, rect: QRectF) -> None:
        p.drawPixmap(rect.x(), rect.y(), self.pix_collapse_tip1 if self._collapse else self.pix_collapse_tip2)
        rect.adjust(10, 0, 0, 0)

    def compute_y_offset(self) -> int:
        y_offset = self.y
        if self.parent:
            y_offset += self.parent.compute_y_offset()
            if self.parent._header:
                y_offset += self.parent.header_height
        return y_offset

    def paint_highlight(self, p: QPainter, params: Label.PaintParams) -> None:
        y_offset = self.compute_y_offset()
        range = self.time_range_to_pixel_range(params, self.t_range)
        y_pixel = params.rect.y() + (self.y + y_offset) * LABEL_PIXEL_HEIGHT_PER_UNIT - params.y_pixel_offset
        rect = QRectF(range.left, y_pixel, range.width, LABEL_PIXEL_HEIGHT_PER_UNIT * self.height)
        p.setPen(self.highlight_pen)
        p.setBrush(self.highlight_brush)
        p.drawRoundedRect(rect, 4, 4)

    # endregion
