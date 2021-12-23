"""Functional Transformers Module."""

from __future__ import annotations

from functools import reduce
from typing import Tuple, Union

import numpy as np

from ...representation import FDataBasis, FDataGrid


def local_averages(
    data: Union[FDataGrid, FDataBasis],
    n_intervals: int,
) -> np.ndarray:
    r"""
    Calculate the local averages of a given data.

    Take functional data as a grid or a basis and performs
    the following map:

    .. math::
        f_1(X) = \frac{1}{|T_1|} \int_{T_1} X(t) dt,\dots, \\
        f_p(X) = \frac{1}{|T_p|} \int_{T_p} X(t) dt

    where {T_1,\dots,T_p} are disjoint intervals of the interval [a,b]

    It is calculated for a given number of intervals,
    which are of equal sizes.
    Args:
        data: FDataGrid or FDataBasis where we want to
        calculate the local averages.
        n_intervals: number of intervals we want to consider.
    Returns:
        ndarray of shape (n_intervals, n_samples, n_dimensions)
        with the transformed data for FDataBasis and (n_intervals, n_samples)
        for FDataGrid.

    Example:

        We import the Berkeley Growth Study dataset.
        We will use only the first 30 samples to make the
        example easy.
        >>> from skfda.datasets import fetch_growth
        >>> dataset = fetch_growth(return_X_y=True)[0]
        >>> X = dataset[:30]

        Then we decide how many intervals we want to consider (in our case 2)
        and call the function with the dataset.
        >>> import numpy as np
        >>> from skfda.exploratory.stats import local_averages
        >>> np.around(local_averages(X, 2), decimals=2)
        array([[  993.98,   950.82,   911.93,   946.44,   887.3 ,   930.18,
                  927.89,   959.72,   928.14,  1002.57,   953.22,   971.53,
                  947.54,   976.26,   988.16,   974.07,   943.67,   965.36,
                  925.48,   931.64,   932.47,   922.56,   927.99,   908.83,
                  930.23,   933.65,   980.25,   919.39,  1013.98,   940.23],
               [ 1506.69,  1339.79,  1317.25,  1392.53,  1331.65,  1340.17,
                 1320.15,  1436.71,  1310.51,  1482.64,  1371.34,  1446.15,
                 1394.84,  1445.87,  1416.5 ,  1434.16,  1418.19,  1421.35,
                 1354.89,  1383.46,  1323.45,  1343.07,  1360.87,  1325.57,
                 1342.55,  1389.99,  1379.43,  1301.34,  1517.04,  1374.91]])
    """
    domain_range = data.domain_range

    left, right = domain_range[0]
    interval_size = (right - left) / n_intervals
    integrated_data = []
    for i in np.arange(left, right, interval_size):
        interval = (i, i + interval_size)
        integrated_data = integrated_data + [
            data.integrate(interval=(interval,)),
        ]
    return np.asarray(integrated_data)


def _calculate_curve_occupation_(
    curve_y_coordinates: np.ndarray,
    curve_x_coordinates: np.ndarray,
    interval: Tuple,
) -> np.ndarray:
    y1, y2 = interval
    first_x_coord = 0
    last_x_coord = 0
    time_x_coord_counter = 0
    inside_interval = False

    for j, y_coordinate in enumerate(curve_y_coordinates[1:]):
        y_coordinate = y_coordinate[0]

        if y1 <= y_coordinate <= y2 and not inside_interval:
            inside_interval = True
            first_x_coord = curve_x_coordinates[j][0]
            last_x_coord = curve_x_coordinates[j][0]
        elif y1 <= y_coordinate <= y2:
            last_x_coord = curve_x_coordinates[j][0]
        elif inside_interval:
            inside_interval = False
            time_x_coord_counter += last_x_coord - first_x_coord
            first_x_coord = 0
            last_x_coord = 0

    return np.array([[time_x_coord_counter]])


def occupation_measure(
    data: Union[FDataGrid, FDataBasis],
    intervals: np.ndarray,
    *,
    n_points: Union[int, None] = None,
) -> np.ndarray:
    r"""
    Calculate the occupation measure of a grid.

    It performs the following map.
        ..math:
            :math:`f_1(X) = |t: X(t)\in T_p|,\dots,|t: X(t)\in T_p|`

        where :math:`{T_1,\dots,T_p}` are disjoint intervals in
        :math:`\mathbb{R}` and | | stands for the Lebesgue measure.

        Args:
            data: FDataGrid or FDataBasis where we want to calculate
            the occupation measure.
            intervals: ndarray of tuples containing the
            intervals we want to consider. The shape should be
            (n_sequences,2)
            n_points: Number of points to evaluate in the domain.
            By default will be used the points defined on the FDataGrid.
            On a FDataBasis this value should be specified.
        Returns:
            ndarray of shape (n_intervals, n_samples)
            with the transformed data.

    Example:
        We will create the FDataGrid that we will use to extract
        the occupation measure
        >>> from skfda.representation import FDataGrid
        >>> import numpy as np
        >>> t = np.linspace(0, 10, 100)
        >>> fd_grid = FDataGrid(
        ...     data_matrix=[
        ...         t,
        ...         2 * t,
        ...         np.sin(t),
        ...     ],
        ...     grid_points=t,
        ... )

        Finally we call to the occupation measure function with the
        intervals that we want to consider. In our case (0.0, 1.0)
        and (2.0, 3.0). We need also to specify the number of points
        we want that the function takes into account to interpolate.
        We are going to use 501 points.
        >>> from skfda.exploratory.stats import occupation_measure
        >>> np.around(
        ...     occupation_measure(
        ...         fd_grid,
        ...         [(0.0, 1.0), (2.0, 3.0)],
        ...         n_points=501,
        ...     ),
        ...     decimals=2,
        ... )
        array([[[ 0.98],
                [ 0.48],
                [ 6.25]],
        <BLANKLINE>
               [[ 0.98],
                [ 0.48],
                [ 0.  ]]])

    """
    if n_points is None:
        if isinstance(data, FDataBasis):
            raise ValueError(
                "Number of points to consider, should be given "
                + " as an argument for a FDataBasis. Instead None was passed.",
            )
        else:
            grid = data.grid_points
    else:
        lower_functional_limit, upper_functional_limit = data.domain_range[0]
        domain_size = upper_functional_limit - lower_functional_limit

    if isinstance(data, FDataGrid):
        time_x_coord_cumulative = np.empty((0, data.data_matrix.shape[0], 1))
    else:
        time_x_coord_cumulative = np.empty((0, data.coefficients.shape[0], 1))

    for interval in intervals:  # noqa: WPS426

        y1, y2 = interval
        if y2 < y1:
            raise ValueError(
                "Interval limits (a,b) should satisfy a <= b. "
                + str(interval) + " doesn't",
            )

        function_x_coordinates = np.empty((1, 1))
        if n_points is None:
            function_x_coordinates = reduce(
                lambda a, b: np.concatenate(
                    (
                        a,
                        np.array([[b]]),
                    ),
                ),
                grid[0],
                function_x_coordinates,
            )[1:]
        else:
            for x_coordinate in np.arange(
                lower_functional_limit,
                upper_functional_limit,
                domain_size / n_points,
            ):
                function_x_coordinates = np.concatenate(
                    (function_x_coordinates, np.array([[x_coordinate]])),
                )

        if n_points is None:
            function_y_coordinates = data.data_matrix
        else:
            function_y_coordinates = data(
                function_x_coordinates,
            )

        time_x_coord_interval = np.empty((0, 1))
        for curve_y_coordinates in function_y_coordinates:

            time_x_coord_count = _calculate_curve_occupation_(  # noqa: WPS317
                curve_y_coordinates,
                function_x_coordinates,
                (y1, y2),
            )
            time_x_coord_interval = np.concatenate(
                (time_x_coord_interval, time_x_coord_count),
            )

        time_x_coord_cumulative = np.concatenate(
            (time_x_coord_cumulative, np.array([time_x_coord_interval])),
        )

    return time_x_coord_cumulative


def number_up_crossings(
    data: FDataGrid,
    levels: np.ndarray,
) -> np.ndarray:
    r"""
    Calculate the number of up crossings to a level of a FDataGrid.

    Let f_1(X) = N_i, where N_i is the number of up crossings of X
    to a level c_i \in \mathbb{R}, i = 1,\dots,p.

    Recall that the process X(t) is said to have an up crossing of c
    at :math:`t_0 > 0` if for some :math:`\epsilon >0`, X(t) $\leq$
    c if t :math:'\in (t_0 - \epsilon, t_0) and X(t) $\geq$ c if
    :math:`t\in (t_0, t_0+\epsilon)`.

    If the trajectories are differentiable, then
    :math:`N_i = card\{t \in[a,b]: X(t) = c_i, X' (t) > 0\}.`

        Args:
            data: FDataGrid where we want to calculate
            the number of up crossings.
            levels: sequence of numbers including the levels
            we want to consider for the crossings.
        Returns:
            ndarray of shape (n_levels, n_samples)\
            with the values of the counters.

    Example:

    We import the Medflies dataset and for simplicity we use
    the first 50 samples.
    >>> from skfda.datasets import fetch_medflies
    >>> dataset = fetch_medflies()
    >>> X = dataset['data'][:50]

    Then we decide the level we want to consider (in our case 40)
    and call the function with the dataset. The output will be the number of
    times each curve cross the level 40 growing.
    >>> from skfda.exploratory.stats import number_up_crossings
    >>> import numpy as np
    >>> number_up_crossings(X, np.asarray([40]))
    array([[[6],
            [3],
            [7],
            [7],
            [3],
            [4],
            [5],
            [7],
            [4],
            [6],
            [4],
            [4],
            [5],
            [6],
            [0],
            [5],
            [1],
            [6],
            [0],
            [7],
            [0],
            [6],
            [2],
            [5],
            [6],
            [5],
            [8],
            [4],
            [3],
            [7],
            [1],
            [3],
            [0],
            [5],
            [2],
            [7],
            [2],
            [5],
            [5],
            [5],
            [4],
            [4],
            [1],
            [2],
            [3],
            [5],
            [3],
            [3],
            [5],
            [2]]])
    """
    curves = data.data_matrix

    distances = np.asarray([
        level - curves
        for level in levels
    ])

    points_greater = distances >= 0
    points_smaller = distances <= 0
    points_smaller_rotated = np.roll(points_smaller, -1, axis=2)

    return np.sum(
        points_greater & points_smaller_rotated,
        axis=2,
    )
