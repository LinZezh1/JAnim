from dataclasses import dataclass
from enum import IntFlag
from typing import Iterable, overload


@dataclass
class AlignedData[T]:
    '''
    数据对齐后的结构，用于 :meth:`~.Item.Data.align_for_interpolate`
    '''
    data1: T
    data2: T
    union: T


class Margins:
    '''
    定义了一组四个边距：左、上、右、下，用于描述矩形周围边框的大小。

    如果直接传入单个数值，则表示为四个方向皆为该值
    '''
    @overload
    def __init__(self, buff: float | tuple[float], /): ...
    @overload
    def __init__(self, left: float, top: float, right: float, bottom: float, /): ...

    def __init__(self, left, top=None, right=None, bottom=None):
        if top is None and right is None and bottom is None:
            self.buff = left
        else:
            self.buff = (left, top, right, bottom)

        self.is_float = not isinstance(self.buff, Iterable)

    @property
    def left(self) -> float:
        return self.buff if self.is_float else self.buff[0]

    @property
    def top(self) -> float:
        return self.buff if self.is_float else self.buff[1]

    @property
    def right(self) -> float:
        return self.buff if self.is_float else self.buff[2]

    @property
    def bottom(self) -> float:
        return self.buff if self.is_float else self.buff[3]


MarginsType = Margins | float | tuple[float]


class Align(IntFlag):
    Center  = 0b0000_0000
    Left    = 0b0000_0001
    Right   = 0b0000_0100
    Top     = 0b0000_1000
    Bottom  = 0b0001_0000
