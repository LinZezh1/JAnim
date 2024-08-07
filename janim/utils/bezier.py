from __future__ import annotations

import inspect
from typing import (Callable, Iterable, NoReturn, Self, Sequence, TypeVar,
                    overload)

import numpy as np
from fontTools.cu2qu.cu2qu import curve_to_quadratic

from janim.constants import DEGREES, NAN_POINT, TAU
from janim.exception import PointError
from janim.typing import Vect, VectArray
from janim.utils.simple_functions import choose
from janim.utils.space_ops import (angle_between_vectors, cross, cross2d,
                                   find_intersection, get_norm, midpoint,
                                   rotation_between_vectors, z_to_vector)
from janim.locale.i18n import get_local_strings

_ = get_local_strings('bezier')

CLOSED_THRESHOLD = 0.001
T = TypeVar("T")


class PathBuilder:
    def __init__(
        self,
        *,
        start_point: Vect | None = None,
        points: VectArray | None = None,
        use_simple_quadratic_approx: bool = False,
    ):
        if start_point is not None and points is not None:
            raise PointError(_('Cannot set both start_point and points at the same time'))
        if start_point is not None:
            self.points_list = [[start_point]]
            self.start_point = start_point
            self.end_point = start_point
        elif points is not None:
            self.points_list = [points]
            self.start_point = points[0]
            self.end_point = points[-1]
        else:
            self.points_list = []
            self.start_point = None
            self.end_point = None

        self.use_simple_quadratic_approx = use_simple_quadratic_approx

    def get(self) -> np.ndarray:
        if not self.points_list:
            return np.empty((0, 3))
        return np.vstack(self.points_list)

    def append(self, points: VectArray, *, line_to_start_point=False) -> Self:
        if line_to_start_point:
            self.points_list.append([(np.array(self.end_point) + np.array(points[0])) * 0.5])
        self.points_list.append(points)
        if self.start_point is None:
            self.start_point = points[0]
        self.end_point = points[-1]
        return self

    def move_to(self, point: Vect) -> Self:
        if self.end_point is None:
            self.points_list.append([point])
        else:
            self.points_list.append([NAN_POINT, point])
        self.start_point = point
        self.end_point = point
        return self

    def line_to(self, point: Vect) -> Self:
        self._raise_if_no_points()
        mid = (self.end_point + point) / 2
        self.points_list.append([mid, point])
        self.end_point = point
        return self

    def conic_to(self, handle: Vect, point: Vect) -> Self:
        self._raise_if_no_points()
        self.points_list.append([handle, point])
        self.end_point = point
        return self

    def cubic_to(
        self,
        handle1: Vect,
        handle2: Vect,
        anchor: Vect
    ) -> Self:
        self._raise_if_no_points()
        if np.isclose(self.end_point, handle1).all():
            self.conic_to(handle2, anchor)
            return
        if np.isclose(handle1, handle2).all():
            self.conic_to(handle1, anchor)
            return
        if np.isclose(handle2, anchor).all():
            self.conic_to(handle1, handle2)
            return

        last = self.end_point
        # Note, this assumes all points are on the xy-plane
        v1 = handle1 - last
        v2 = anchor - handle2
        angle = angle_between_vectors(v1, v2)
        if self.use_simple_quadratic_approx and angle < 45 * DEGREES:
            quad_approx = [last, *find_intersection(last, v1, anchor, -v2), anchor]
        else:
            quad_approx = get_quadratic_approximation_of_cubic(
                last, handle1, handle2, anchor
            )
        self.points_list.append(quad_approx[1:])
        self.end_point = quad_approx[-1]
        return self

    def arc_to(self, point: Vect, angle: float, n_components: int | None = None, threshold: float = 1e-3) -> Self:
        self._raise_if_no_points()

        if abs(angle) < threshold:
            self.line_to(point)
            return self

        # Assign default value for n_components
        if n_components is None:
            n_components = int(np.ceil(8 * abs(angle) / TAU))

        arc_points = quadratic_bezier_points_for_arc(angle, n_components)
        target_vect = point - self.end_point
        curr_vect = arc_points[-1] - arc_points[0]

        arc_points = arc_points @ rotation_between_vectors(curr_vect, target_vect).T
        arc_points *= get_norm(target_vect) / get_norm(curr_vect)
        arc_points += (self.end_point - arc_points[0])
        self.append(arc_points[1:])
        return self

    def close_path(self) -> Self:
        self._raise_if_no_points()
        self.line_to(self.start_point)
        return self

    def _raise_if_no_points(self) -> None | NoReturn:
        if self.end_point is None:
            name = inspect.currentframe().f_back.f_code.co_name
            raise PointError(
                _('PathBuilder must be initialized with start_point or points during construction, '
                  'or have move_to as the first call, otherwise {name} cannot be invoked')
                .format(name=name)
            )


def quadratic_bezier_points_for_arc(
    angle: float,
    start_angle: float = 0,
    n_components: int = 8
) -> np.ndarray:
    '''得到使用二次贝塞尔曲线模拟的圆弧'''
    n_points = 2 * n_components + 1
    angles = np.linspace(start_angle, start_angle + angle, n_points)
    points = np.array([np.cos(angles), np.sin(angles), np.zeros(n_points)]).T
    # Adjust handles
    theta = angle / n_components
    points[1::2] /= np.cos(theta / 2)
    return points


def bezier(
    points: Iterable[float | np.ndarray]
) -> Callable[[float], float | np.ndarray]:
    n = len(points) - 1

    def result(t):
        return sum(
            ((1 - t)**(n - k)) * (t**k) * choose(n, k) * point
            for k, point in enumerate(points)
        )

    return result


def partial_bezier_points(
    points: Sequence[np.ndarray],
    a: float,
    b: float
) -> list[float]:
    """
    Given an list of points which define
    a bezier curve, and two numbers 0<=a<b<=1,
    return an list of the same size, which
    describes the portion of the original bezier
    curve on the interval [a, b].

    This algorithm is pretty nifty, and pretty dense.
    """
    if a == 1:
        return [points[-1]] * len(points)

    a_to_1 = [
        bezier(points[i:])(a)
        for i in range(len(points))
    ]
    end_prop = (b - a) / (1. - a)
    return [
        bezier(a_to_1[:i + 1])(end_prop)
        for i in range(len(points))
    ]


# Shortened version of partial_bezier_points just for quadratics,
# since this is called a fair amount
def partial_quadratic_bezier_points(
    points: Sequence[np.ndarray],
    a: float,
    b: float
) -> list[np.ndarray]:
    if a == 1:
        return 3 * [points[-1]]

    def curve(t):
        return points[0] * (1 - t) * (1 - t) + 2 * points[1] * t * (1 - t) + points[2] * t * t
    # bezier(points)
    h0 = curve(a) if a > 0 else points[0]
    h2 = curve(b) if b < 1 else points[2]
    h1_prime = (1 - a) * points[1] + a * points[2]
    end_prop = (b - a) / (1. - a)
    h1 = (1 - end_prop) * h0 + end_prop * h1_prime
    return [h0, h1, h2]


# Linear interpolation variants

@overload
def interpolate(start: T, end: T, alpha: float) -> T: ...
@overload
def interpolate(start, end, alpha: np.ndarray) -> np.ndarray: ...


def interpolate(start, end, alpha):
    return (1 - alpha) * start + alpha * end


def outer_interpolate(
    start: np.ndarray | float,
    end: np.ndarray | float,
    alpha: np.ndarray | float,
) -> T:
    result = np.outer(1 - alpha, start) + np.outer(alpha, end)
    return result.reshape((*np.shape(alpha), *np.shape(start)))


def set_array_by_interpolation(
    arr: np.ndarray,
    arr1: np.ndarray,
    arr2: np.ndarray,
    alpha: float,
    interp_func: Callable[[np.ndarray, np.ndarray, float], np.ndarray] = interpolate
) -> np.ndarray:
    arr[:] = interp_func(arr1, arr2, alpha)
    return arr


def integer_interpolate(
    start: T,
    end: T,
    alpha: float
) -> tuple[int, float]:
    """
    alpha is a float between 0 and 1.  This returns
    an integer between start and end (inclusive) representing
    appropriate interpolation between them, along with a
    "residue" representing a new proportion between the
    returned integer and the next one of the
    list.

    For example, if start=0, end=10, alpha=0.46, This
    would return (4, 0.6).
    """
    if alpha >= 1:
        return (end - 1, 1.0)
    if alpha <= 0:
        return (start, 0)
    value = int(interpolate(start, end, alpha))
    residue = ((end - start) * alpha) % 1
    return (value, residue)


def mid(start: T, end: T) -> T:
    return (start + end) / 2.0


def inverse_interpolate(start: T, end: T, value: T) -> float:
    return np.true_divide(value - start, end - start)


def match_interpolate(
    new_start: T,
    new_end: T,
    old_start: T,
    old_end: T,
    old_value: T
) -> T:
    return interpolate(
        new_start, new_end,
        inverse_interpolate(old_start, old_end, old_value)
    )


def approx_smooth_quadratic_bezier_handles(
    points: Sequence[np.ndarray]
) -> np.ndarray | list[np.ndarray]:
    '''
    Figuring out which bezier curves most smoothly connect a sequence of points.

    Given three successive points, P0, P1 and P2, you can compute that by defining
    h = (1/4) P0 + P1 - (1/4)P2, the bezier curve defined by (P0, h, P1) will pass
    through the point P2.

    So for a given set of four successive points, P0, P1, P2, P3, if we want to add
    a handle point h between P1 and P2 so that the quadratic bezier (P1, h, P2) is
    part of a smooth curve passing through all four points, we calculate one solution
    for h that would produce a parbola passing through P3, call it smooth_to_right, and
    another that would produce a parabola passing through P0, call it smooth_to_left,
    and use the midpoint between the two.
    '''
    if len(points) == 2:
        return midpoint(*points)
    smooth_to_right, smooth_to_left = [
        0.25 * ps[0:-2] + ps[1:-1] - 0.25 * ps[2:]
        for ps in (points, points[::-1])
    ]
    if np.isclose(points[0], points[-1]).all():
        last_str = 0.25 * points[-2] + points[-1] - 0.25 * points[1]
        last_stl = 0.25 * points[1] + points[0] - 0.25 * points[-2]
    else:
        last_str = smooth_to_left[0]
        last_stl = smooth_to_right[0]
    handles = 0.5 * np.vstack([smooth_to_right, [last_str]])
    handles += 0.5 * np.vstack([last_stl, smooth_to_left[::-1]])
    return handles


def smooth_quadratic_path(anchors: VectArray) -> np.ndarray:
    '''
    Returns a path defining a smooth quadratic bezier spline
    through anchors.
    '''
    if len(anchors) < 2:
        return anchors
    elif len(anchors) == 2:
        return np.array([anchors[0], anchors.mean(1), anchors[2]])

    is_flat = (anchors[:, 2] == 0).all()
    if not is_flat:
        normal = cross(anchors[2] - anchors[1], anchors[1] - anchors[0])
        rot = z_to_vector(normal)
        anchors = np.dot(anchors, rot)
        shift = anchors[0, 2]
        anchors[:, 2] -= shift
    h1s, h2s = get_smooth_cubic_bezier_handle_points(anchors)
    quads = [anchors[0, :2]]
    for cub_bs in zip(anchors[:-1], h1s, h2s, anchors[1:]):
        # Try to use fontTools curve_to_quadratic
        new_quads = curve_to_quadratic(
            [b[:2] for b in cub_bs],
            max_err=0.1 * get_norm(cub_bs[3] - cub_bs[0])
        )
        # Otherwise fall back on home baked solution
        if new_quads is None or len(new_quads) % 2 == 0:
            new_quads = get_quadratic_approximation_of_cubic(*cub_bs)[:, :2]
        quads.extend(new_quads[1:])
    new_path = np.zeros((len(quads), 3))
    new_path[:, :2] = quads
    if not is_flat:
        new_path[:, 2] += shift
        new_path = np.dot(new_path, rot.T)
    return new_path


def get_smooth_cubic_bezier_handle_points(
    points: VectArray
) -> tuple[np.ndarray, np.ndarray]:

    from scipy import linalg

    points = np.array(points)
    num_handles = len(points) - 1
    dim = points.shape[1]
    if num_handles < 1:
        return np.zeros((0, dim)), np.zeros((0, dim))
    # Must solve 2*num_handles equations to get the handles.
    # l and u are the number of lower an upper diagonal rows
    # in the matrix to solve.
    l, u = 2, 1
    # diag is a representation of the matrix in diagonal form
    # See https://www.particleincell.com/2012/bezier-splines/
    # for how to arrive at these equations
    diag = np.zeros((l + u + 1, 2 * num_handles))
    diag[0, 1::2] = -1
    diag[0, 2::2] = 1
    diag[1, 0::2] = 2
    diag[1, 1::2] = 1
    diag[2, 1:-2:2] = -2
    diag[3, 0:-3:2] = 1
    # last
    diag[2, -2] = -1
    diag[1, -1] = 2
    # This is the b as in Ax = b, where we are solving for x,
    # and A is represented using diag.  However, think of entries
    # to x and b as being points in space, not numbers
    b = np.zeros((2 * num_handles, dim))
    b[1::2] = 2 * points[1:]
    b[0] = points[0]
    b[-1] = points[-1]

    def solve_func(b):
        return linalg.solve_banded((l, u), diag, b)

    use_closed_solve_function = is_closed(points)
    if use_closed_solve_function:
        # Get equations to relate first and last points
        matrix = diag_to_matrix((l, u), diag)
        # last row handles second derivative
        matrix[-1, [0, 1, -2, -1]] = [2, -1, 1, -2]
        # first row handles first derivative
        matrix[0, :] = np.zeros(matrix.shape[1])
        matrix[0, [0, -1]] = [1, 1]
        b[0] = 2 * points[0]
        b[-1] = np.zeros(dim)

        def closed_curve_solve_func(b):
            return linalg.solve(matrix, b)

    handle_pairs = np.zeros((2 * num_handles, dim))
    for i in range(dim):
        if use_closed_solve_function:
            handle_pairs[:, i] = closed_curve_solve_func(b[:, i])
        else:
            handle_pairs[:, i] = solve_func(b[:, i])
    return handle_pairs[0::2], handle_pairs[1::2]


def diag_to_matrix(
    l_and_u: tuple[int, int],
    diag: np.ndarray
) -> np.ndarray:
    '''
    Converts array whose rows represent diagonal
    entries of a matrix into the matrix itself.
    See scipy.linalg.solve_banded
    '''
    l, u = l_and_u
    dim = diag.shape[1]
    matrix = np.zeros((dim, dim))
    for i in range(l + u + 1):
        np.fill_diagonal(
            matrix[max(0, i - u):, max(0, u - i):],
            diag[i, max(0, u - i):]
        )
    return matrix


def is_closed(points: Sequence[np.ndarray]) -> bool:
    return np.allclose(points[0], points[-1])


# Given 4 control points for a cubic bezier curve (or arrays of such)
# return control points for 2 quadratics (or 2n quadratics) approximating them.
def get_quadratic_approximation_of_cubic(
    a0: Vect,
    h0: Vect,
    h1: Vect,
    a1: Vect
) -> np.ndarray:
    a0 = np.array(a0, ndmin=2)
    h0 = np.array(h0, ndmin=2)
    h1 = np.array(h1, ndmin=2)
    a1 = np.array(a1, ndmin=2)
    # Tangent vectors at the start and end.
    T0 = h0 - a0
    T1 = a1 - h1

    # Search for inflection points.  If none are found, use the
    # midpoint as a cut point.
    # Based on http://www.caffeineowl.com/graphics/2d/vectorial/cubic-inflexion.html
    has_infl = np.ones(len(a0), dtype=bool)

    p = h0 - a0
    q = h1 - 2 * h0 + a0
    r = a1 - 3 * h1 + 3 * h0 - a0

    a = cross2d(q, r)
    b = cross2d(p, r)
    c = cross2d(p, q)

    disc = b * b - 4 * a * c
    has_infl &= (disc > 0)
    sqrt_disc = np.sqrt(np.abs(disc))
    settings = np.seterr(all='ignore')
    ti_bounds = []
    for sgn in [-1, +1]:
        ti = (-b + sgn * sqrt_disc) / (2 * a)
        ti[a == 0] = (-c / b)[a == 0]
        ti[(a == 0) & (b == 0)] = 0
        ti_bounds.append(ti)
    ti_min, ti_max = ti_bounds
    np.seterr(**settings)
    ti_min_in_range = has_infl & (0 < ti_min) & (ti_min < 1)
    ti_max_in_range = has_infl & (0 < ti_max) & (ti_max < 1)

    # Choose a value of t which starts at 0.5,
    # but is updated to one of the inflection points
    # if they lie between 0 and 1

    t_mid = 0.5 * np.ones(len(a0))
    t_mid[ti_min_in_range] = ti_min[ti_min_in_range]
    t_mid[ti_max_in_range] = ti_max[ti_max_in_range]

    m, n = a0.shape
    t_mid = t_mid.repeat(n).reshape((m, n))

    # Compute bezier point and tangent at the chosen value of t
    mid = bezier([a0, h0, h1, a1])(t_mid)
    Tm = bezier([h0 - a0, h1 - h0, a1 - h1])(t_mid)

    # Intersection between tangent lines at end points
    # and tangent in the middle
    i0 = find_intersection(a0, T0, mid, Tm)
    i1 = find_intersection(a1, T1, mid, Tm)

    m, n = np.shape(a0)
    result = np.zeros((5 * m, n))
    result[0::5] = a0
    result[1::5] = i0
    result[2::5] = mid
    result[3::5] = i1
    result[4::5] = a1
    return result
