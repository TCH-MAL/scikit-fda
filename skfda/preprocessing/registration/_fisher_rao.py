
from __future__ import annotations

import warnings
from typing import Any, Callable, Optional, Union

from sklearn.utils.validation import check_is_fitted

from ... import FDataGrid
from ..._utils import check_is_univariate, invert_warping, normalize_scale
from ...exploratory.stats import fisher_rao_karcher_mean
from ...exploratory.stats._fisher_rao import _elastic_alignment_array
from ...misc.operators import SRSF
from ...representation._typing import ArrayLike
from ...representation.interpolation import SplineInterpolation
from .base import RegistrationTransformer

_MeanType = Callable[[FDataGrid], FDataGrid]


class ElasticFisherRaoRegistration(RegistrationTransformer):
    r"""Align a FDatagrid using the SRSF framework.

    Let :math:`f` be a function of the functional data object wich will be
    aligned to the template :math:`g`. Calculates the warping wich minimises
    the Fisher-Rao distance between :math:`g` and the registered function
    :math:`f^*(t)=f(\gamma^*(t))=f \circ \gamma^*`.

    .. math::
        \gamma^* = argmin_{\gamma \in \Gamma} d_{\lambda}(f \circ
        \gamma, g)

    Where :math:`d_{\lambda}` denotes the extended Fisher-Rao distance with a
    penalty term, used to control the amount of warping.

    .. math::
        d_{\lambda}^2(f \circ \gamma, g) = \| SRSF(f \circ \gamma)
        \sqrt{\dot{\gamma}} - SRSF(g)\|_{\mathbb{L}^2}^2 + \lambda
        \mathcal{R}(\gamma)

    In the implementation it is used as penalty term

    .. math::
        \mathcal{R}(\gamma) = \|\sqrt{\dot{\gamma}}- 1 \|_{\mathbb{L}^2}^2

    Wich restrict the amount of elasticity employed in the alignment.

    The registered function :math:`f^*(t)` can be calculated using the
    composition :math:`f^*(t)=f(\gamma^*(t))`.

    If the template is not specified it is used the Karcher mean of the set of
    functions under the elastic metric to perform the alignment, also known as
    `elastic mean`, wich is the local minimum of the sum of squares of elastic
    distances. See :func:`~elastic_mean`.

    In :footcite:`srivastava+klassen_2016_analysis_elastic` are described
    extensively the algorithms employed and the SRSF framework.

    Args:
        template (str, :class:`FDataGrid` or callable, optional): Template to
            align the curves. Can contain 1 sample to align all the curves to
            it or the same number of samples than the fdatagrid. By default
            `elastic mean`, in which case :func:`elastic_mean` is called.
        penalty_term (float, optional): Controls the amount of elasticity.
            Defaults to 0.
        output_points (array_like, optional): Set of points where the
            functions are evaluated, by default uses the sample points of the
            fdatagrid which will be transformed.
        grid_dim (int, optional): Dimension of the grid used in the DP
            alignment algorithm. Defaults 7.

    Attributes:
        template\_: Template learned during fitting,
            used for alignment in :meth:`transform`.
        warping\_: Warping applied during the last
            transformation.

    References:
        .. footbibliography::

    Examples:
        Elastic registration of with train/test sets.

        >>> from skfda.preprocessing.registration import (
        ...     ElasticFisherRaoRegistration,
        ... )
        >>> from skfda.datasets import make_multimodal_samples
        >>> X_train = make_multimodal_samples(n_samples=15, random_state=0)
        >>> X_test = make_multimodal_samples(n_samples=3, random_state=1)

        Fit the transformer, which learns the elastic mean of the train
        set as template.

        >>> elastic_registration = ElasticFisherRaoRegistration()
        >>> elastic_registration.fit(X_train)
        ElasticFisherRaoRegistration(...)

        Registration of the test set.

        >>> elastic_registration.transform(X_test)
        FDataGrid(...)

    """

    def __init__(
        self,
        *,
        template: Union[FDataGrid, _MeanType] = fisher_rao_karcher_mean,
        penalty: float = 0,
        output_points: Optional[ArrayLike] = None,
        grid_dim: int = 7,
    ) -> None:
        self.template = template
        self.penalty = penalty
        self.output_points = output_points
        self.grid_dim = grid_dim

    def fit(self, X: FDataGrid, y: None = None) -> RegistrationTransformer:
        """Fit the transformer.

        Learns the template used during the transformation.

        Args:
            X: Functional observations used as training samples. If the
                template provided is a FDataGrid this argument is ignored, as
                it is not necessary to learn the template from the training
                data.
            y: Present for API conventions.

        Returns:
            self.

        """
        if isinstance(self.template, FDataGrid):
            self.template_ = self.template  # Template already constructed
        else:
            self.template_ = self.template(X)

        # Constructs the SRSF of the template
        srsf = SRSF(output_points=self.output_points, initial_value=0)
        self._template_srsf = srsf.fit_transform(self.template_)

        return self

    def transform(self, X: FDataGrid, y: None = None) -> FDataGrid:
        """Apply elastic registration to the data.

        Args:
            X: Functional data to be registered.
            y: Present for API conventions.

        Returns:
            Registered samples.

        """
        check_is_fitted(self, '_template_srsf')
        check_is_univariate(X)

        if (
            len(self._template_srsf) != 1
            and len(X) != len(self._template_srsf)
        ):

            raise ValueError(
                "The template should contain one sample to align "
                "all the curves to the same function or the "
                "same number of samples than X.",
            )

        srsf = SRSF(output_points=self.output_points, initial_value=0)
        fdatagrid_srsf = srsf.fit_transform(X)

        # Points of discretization
        if self.output_points is None:
            output_points = fdatagrid_srsf.grid_points[0]
        else:
            output_points = self.output_points

        # Discretizacion in evaluation points
        q_data = fdatagrid_srsf(output_points)[..., 0]
        template_data = self._template_srsf(output_points)[..., 0]

        if q_data.shape[0] == 1:
            q_data = q_data[0]

        if template_data.shape[0] == 1:
            template_data = template_data[0]

        # Values of the warping
        gamma = _elastic_alignment_array(
            template_data,
            q_data,
            normalize_scale(output_points),
            self.penalty,
            self.grid_dim,
        )

        # Normalize warping to original interval
        gamma = normalize_scale(
            gamma,
            a=output_points[0],
            b=output_points[-1],
        )

        # Interpolation
        interpolation = SplineInterpolation(
            interpolation_order=3,
            monotone=True,
        )

        self.warping_ = FDataGrid(
            gamma,
            output_points,
            interpolation=interpolation,
        )

        return X.compose(self.warping_, eval_points=output_points)

    def inverse_transform(self, X: FDataGrid, y: None = None) -> FDataGrid:
        r"""
        Reverse the registration procedure previosly applied.

        Let :math:`gamma(t)` the warping applied to construct a registered
        functional datum :math:`f^*(t)=f(\gamma(t))`.

        Given a functional datum :math:`f^*(t) it is computed
        :math:`\gamma^{-1}(t)` to reverse the registration procedure
        :math:`f(t)=f^*(\gamma^{-1}(t))`.

        Args:
            X: Functional data to apply the reverse
                transform.
            y: Present for API conventions.

        Returns:
            Functional data compose by the inverse warping.

        Raises:
            ValueError: If the warpings :math:`\gamma` were not build via
                :meth:`transform` or if the number of samples of `X` is
                different than the number of samples of the dataset
                previously transformed.

        Examples:
            Center the datasets taking into account the misalignment.

            >>> from skfda.preprocessing.registration import (
            ...     ElasticFisherRaoRegistration,
            ... )
            >>> from skfda.datasets import make_multimodal_samples
            >>> X = make_multimodal_samples(random_state=0)

            Registration of the dataset.

            >>> elastic_registration = ElasticFisherRaoRegistration()
            >>> X = elastic_registration.fit_transform(X)

            Substract the elastic mean build as template during the
            registration and reverse the transformation.

            >>> X = X - elastic_registration.template_
            >>> X_center = elastic_registration.inverse_transform(X)
            >>> X_center
            FDataGrid(...)


        See also:
            :func:`invert_warping`

        """
        warping = getattr(self, 'warping_', None)

        if warping is None:
            raise ValueError(
                "Data must be previosly transformed to apply the "
                "inverse transform",
            )
        elif len(X) != len(warping):
            raise ValueError(
                "Data must contain the same number of samples "
                "than the dataset previously transformed",
            )

        inverse_warping = invert_warping(warping)

        return X.compose(inverse_warping, eval_points=self.output_points)


class ElasticRegistration(ElasticFisherRaoRegistration):

    def __init__(
        self,
        template: Union[FDataGrid, _MeanType] = fisher_rao_karcher_mean,
        penalty: float = 0,
        output_points: Optional[ArrayLike] = None,
        grid_dim: int = 7,
    ) -> None:
        warnings.warn(
            "ElasticRegistration is deprecated. "
            "Use ElasticFisherRaoRegistration instead.",
            DeprecationWarning,
        )
        super().__init__(
            template=template,
            penalty=penalty,
            output_points=output_points,
            grid_dim=grid_dim,
        )
