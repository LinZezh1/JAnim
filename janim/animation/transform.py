from __future__ import annotations
from typing import Callable, Optional

from janim.constants import *
from janim.animation.animation import ItemAnimation
from janim.items.item import Item
from janim.utils.paths import straight_path, path_along_arc

class Transform(ItemAnimation):
    '''
    创建从 `item` 至 `target_item` 的插值动画

    - 改变的是 `item` 的数据，以呈现插值效果
    - `path_arc` 和 `path_arc_axis` 可以指定插值的圆弧路径的角度，若不传入则是直线
    - 也可以直接传入 `path_func` 来指定路径方法

    另请参考 `ReplacementTransform`
    '''
    def __init__(
        self,
        item: Item,
        target_item: Item | None,
        path_arc: float = 0,
        path_arc_axis: np.ndarray = OUT,
        path_func: Optional[Callable[[np.ndarray, np.ndarray, float], np.ndarray]] = None,
        call_immediately: bool = False,
        replace: bool = False,
        **kwargs
    ) -> None:
        super().__init__(target_item if replace else item, **kwargs)
        self.item = item
        self.target_item = target_item
        self.item_copy = None
        self.target_copy = self.target_item.copy() if call_immediately else None

        self.path_func = path_func or self.create_path_func(path_arc, path_arc_axis)
        self.replace = replace

    @staticmethod
    def create_path_func(
        path_arc: float,
        path_arc_axis: np.ndarray
    ) -> Callable[[np.ndarray, np.ndarray, float], np.ndarray]:
        if path_arc == 0:
            return straight_path
        return path_along_arc(
            path_arc,
            path_arc_axis
        )
    
    def create_interpolate_datas(self) -> list:
        if self.target_copy is None:
            self.target_copy = self.target_item.copy()
        self.item.align_for_transform(self.target_copy)
        if self.item_copy is None:
            self.item_copy = self.item.copy()

        return (
            self.item_copy.get_family(), 
            self.target_copy.get_family(),
            ItemAnimation.compute_npdata_to_copy_and_interpolate(self.item_copy, self.target_copy),
            ItemAnimation.compute_triangulation_equals(self.item, self.target_item)
        )
    
    def is_null_item(self, item: Item, interpolate_data: tuple) -> bool:
        item1, item2, _ = interpolate_data
        return not item1.has_points() and not item2.has_points()
    
    def begin(self) -> None:
        if self.replace:
            parent = self.item.parent
            if parent:
                parent.replace_subitem(self.item, self.target_item)
        super().begin()
    
    def interpolate_subitem(self, item: Item, interpolate_data: tuple, alpha: float) -> None:
        item1, item2, npdata_to_copy_and_interpolate, tri_equals = interpolate_data
        item.interpolate(item1, item2, alpha, self.path_func, npdata_to_copy_and_interpolate)
        if tri_equals:
            item.mark_flag(item.get_triangulation, flag=False)

class ReplacementTransform(Transform):
    '''
    与 `Transform` 类似，但是在执行后变为使用目标物件操作

    例如，使用 `ReplacementTransform(a, b)` 后，b物件 替代了 a物件 的操作

    另请参考 `Transform`
    '''
    def __init__(
        self,
        item: Item,
        target_item: Item,
        replace: bool = True,
        **kwargs
    ) -> None:
        super().__init__(item, target_item, replace=replace, **kwargs)

class MoveToTarget(Transform):
    '''显示从当前状态变为 物件target 的动画'''
    def __init__(self, item: Item, target_key='', **kwargs) -> None:
        if target_key not in item.targets:
            raise Exception(
                'MoveToTarget called on item '
                'without generate its target before'
            )
        super().__init__(item, item.targets[target_key], **kwargs)

class MethodAnimation(Transform):
    '''
    给 `Item.anim` 使用，请参考 `Item.anim` 的注释
    '''
    def __init__(
        self,
        item: Item,
        call_immediately: bool = False,
        **kwargs
    ) -> None:
        super().__init__(item, item, **kwargs)
        self.call_immediately = call_immediately
        if not call_immediately:
            self.methods_to_call = []

    def begin(self) -> None:
        if not self.call_immediately:
            self.target_copy = self.item.copy()
            for method_name, method_args, method_kwargs in self.methods_to_call:
                method = getattr(self.target_copy, method_name)
                method(*method_args, **method_kwargs)
        super().begin()
    
    def __getattr__(self, method_name: str) -> Callable:
        def update_target(*method_args, **method_kwargs):
            if self.call_immediately:
                method = getattr(self.target_copy, method_name)
                method(*method_args, **method_kwargs)
            else:
                self.methods_to_call.append((method_name, method_args, method_kwargs))
            return self
        
        return update_target
