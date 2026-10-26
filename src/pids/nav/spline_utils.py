# Copyright 2025, Hugo Melchers, Eindhoven University of Technology

from __future__ import annotations


# Standard
from typing import Tuple, Optional

import torch
from torch import nn
from math import log


class BSpline(nn.Module):

    dim = 1


    def __init__(
        self, *,
        lims:Tuple[float, float],
        n_segments:int,
        degree:int,
        max_ratio:float = 1.0,
        log_widths:Optional[torch.Tensor] = None
    ):
        """
        Creates a new BSpline that forms a basis of the interval [a, b],
        split up into `nr_segments` intervals. The B-splines have the given
        `degree`. Note that the total number of functions is then not equal to
        `n_segments`, but `n_segments + degree`.

        The argument `max_ratio` affects the random initialisation of the
        B-splines. This gives the maximum allowed ratio of the largest to
        shortest segments that partition the interval [a, b]. If max_ratio=1,
        then all intervals must have the same length, meaning that the
        initialisation is uniform. By default, the largest segment is at
        most 5 times as long as the shortest interval, which corresponds to
        max_ratio=0.2 but can also be achieved with max_ratio=5.

        If `log_widths` is given, then the returned layer is not trainable, but
        instead contains the specified log_widths. In this case, the length of
        this array should equal `n_segments`, and the value of max_ratio, if
        present, will be ignored.

        For example, BSpline((0, 1), 5, 3, 1) creates a B-spline basis
        with 5 equal knot spans and cubic splines, so 8 basis functions in
        total, all supported on the interval [0, 1].

        Notes:
        -   The internal parameters of the layer have the same precision (i.e. 32
            vs 64 bit) as log_widths, or 32-bit if log_widths is not given. To
            then evaluate the model in 64-bit precision, use
            `layer = layer.to(torch.float64)`
        -   By default, this creates a B-spline layer with a learnable knot
            vector. Setting max_ratio=0 creates a uniform B-spline basis, but
            this knot vector is still trainable so the basis will not stay
            exactly uniform if trained as part of a model. To create a uniform
            basis with non-trainable knot_vector, use
            `BSpline.uniform(lims, n_segments, degree)`.
        """

        super(BSpline, self).__init__()

        if n_segments < 2:
            raise TypeError(
                f"BSplineLayer1D: n_segments must be greater than 1, but got {n_segments}"
            )

        self.n_segments = n_segments
        self.degree = degree
        self.lims = lims

        if log_widths is not None:

            self.dtype = log_widths.dtype

            assert log_widths.numel() == n_segments, (
                f"BSplineLayer got n_segments={n_segments}, but log_widths "
                f"with {log_widths.numel()} elements"
            )

            if isinstance(log_widths, nn.Parameter):
                self.log_widths = log_widths

            elif isinstance(log_widths, torch.Tensor):
                self.register_buffer("log_widths", log_widths)
                knot_vector = self.get_knot_vector()
                self.register_buffer("knot_vector", knot_vector)

            else:
                raise TypeError(
                    f"BSplineLayer1D: expected `log_widths` to be None, a nn.Parameter, or torch.Tensor (got type {type(log_widths)})"
                )

        else:
            self.log_widths = nn.Parameter(torch.rand(n_segments) * log(max_ratio))
            self.dtype = torch.float32


    @staticmethod
    def uniform(
        lims:Tuple[float, float],
        n_segments:int,
        degree:int,
        dtype:torch.dtype=torch.float32
    ) -> BSpline:
        return BSpline(
            lims=lims,
            n_segments=n_segments,
            degree=degree,
            log_widths=torch.zeros(
                (n_segments,),
                dtype=dtype
            )
        )


    def get_knot_vector(self):
        """
        Gets the knot vector of the B-spline layer. The knot vector is not
        directly a parameter of the model, because the distance between
        subsequent knots should not become too small. Furthermore, the first
        and last `degree + 1` should always equal the left and right endpoint
        of the interval [a, b], respectively. For these reasons, the model
        learns the logarithms of the widths of the intervals, up to some
        constant.
        """

        if hasattr(self, "knot_vector"):
            return self.knot_vector

        widths = self.log_widths.exp()
        a, b = self.lims
        widths = widths * (b - a) / widths.sum()
        knots_internal = widths.cumsum_(0) + a

        device = knots_internal.device

        knots = torch.cat(
            (
                torch.full((self.degree + 1,), a, device=device, dtype=self.dtype),
                knots_internal.to(dtype=self.dtype),
                torch.full((self.degree,), b, device=device, dtype=self.dtype),
            )
        )

        return knots


    def get_partition(self):
        """
        Gets the points that partition the interval on which this function is
        defined. This is the same as the knot vector, except that the
        multiplicities of the end points are just 1, instead of being higher
        depending on the degree.
        """
        widths = self.log_widths.exp()
        a, b = self.lims
        widths = widths * (b - a) / widths.sum()
        knots_internal = widths.cumsum_(0) + a
        knots = torch.cat(
            (
                torch.full((1,), a, device=knots_internal.device, dtype=self.dtype),
                knots_internal,
            )
        )
        return knots


    def forward(self, x):
        """
        Compute the b-splines at the given x-values. The output is an N×M
        array, where N = length(x) and M is the number of basis functions.
        """
        knots = self.get_knot_vector().unsqueeze(0)

        return BSpline._bspline_get_values(
            knots=knots,
            degree=self.degree,
            x=x
        )


    def derivative(self, x, k=1):
        """
        Compute the k-th derivative (default 1) of the basis functions on the
        given points.
        """
        degree = self.degree
        knots = self.get_knot_vector().unsqueeze(0)
        nf = knots.numel() - degree - 1
        W = torch.diag(torch.ones(nf, dtype=x.dtype, device=x.device))
        return BSpline._bspline_get_derivatives(
            knots=knots,
            degree=degree,
            k=k,
            x=x,
            W=W
        )


    @staticmethod
    def _bspline_get_values(
        *,
        knots: torch.Tensor,
        degree: int,
        x: torch.Tensor
    ) -> torch.Tensor:

        # NOTE:
        #   This function originally defaulted to x.dtype;
        #   however, this led to inconsistent result.dtype
        #   depending on whether the loop (degree>0?) was executed 
        #   because `knots` may have a different dtype.
        # dtype = (knots[0,0] + x[0]).dtype

        _dtype = x.dtype
        
        if _dtype != knots.dtype:
            raise Warning(
                "The input tensor `x` and the knot vector `knots` have "
                "different dtypes, %s and %s, respectively. Casting knots to %s",
                str(_dtype),
                str(knots.dtype),
                str(_dtype)
            )

        _knots = knots.to(dtype=_dtype)

        Nx = x.numel()
        x = x.unsqueeze(-1)
        padding = torch.full((Nx, degree), False, device=x.device)

        result = torch.cat(
            (
                padding,
                x < _knots[:, degree + 1],
                (_knots[:, degree + 1 : -degree - 2] <= x)
                * (x < _knots[:, degree + 2 : -degree - 1]),
                _knots[:, -degree - 2] <= x,
                padding,
            ),
            dim=1,
        ).to(dtype=_dtype)

        eps = torch.tensor(1e-16, dtype=_dtype, device=x.device)

        for deg in range(1, degree + 1):
            nf = _knots.numel() - deg - 1
            a = _knots[:, 0 : nf + 1]
            b = _knots[:, deg : (1 + deg + nf)]
            l = torch.maximum(b - a, eps)
            v1 = result[:, 0:nf] * (x - a[:, :-1]) / l[:, :-1]
            v2 = result[:, 1 : (nf + 1)] * (b[:, 1:] - x) / l[:, 1:]
            result = v1 + v2

        return result


    @staticmethod
    def _bspline_get_derivatives(
        *,
        knots,
        degree,
        k,
        x,
        W
    ):
        _dtype = x.dtype

        if _dtype != knots.dtype:
            raise Warning(
                "The input tensor `x` and the knot vector `knots` have "
                "different dtypes, %s and %s, respectively. Casting knots to %s",
                str(_dtype),
                str(knots.dtype),
                str(_dtype)
            )

        if _dtype != W.dtype:
            raise Warning(
                "The input tensor `x` and the input tensor `W` have "
                "different dtypes, %s and %s, respectively. Casting W to %s",
                str(_dtype),
                str(W.dtype),
                str(_dtype)
            )

        _W = W.to(dtype=_dtype)
        _knots = knots.to(dtype=_dtype)

        nf = _knots.numel() - degree - 1
        if k == 0:
            return BSpline._bspline_get_values(
                knots=_knots,
                degree=degree,
                x=x
            ) @ _W
        elif k > degree:
            return torch.zeros((x.numel(), nf), dtype=_dtype, device=x.device)
        else:
            # The derivatives of a degree-p B-spline basis can be expressed as linear combinations of degree (p-1) B-spline basis functions.
            # To evaluate the lower-order functions, I also remove the first and last knot, since the lower degree also expects lower multiplicities of the start and end knot.
            eps = torch.tensor(1e-10, dtype=_dtype, device=x.device)
            a1 = _knots[:, 1:nf]
            b1 = _knots[:, degree + 1 : -1]
            W2 = degree * _W.diff(dim=0) / torch.maximum(b1 - a1, eps).T
            return BSpline._bspline_get_derivatives(
                knots=_knots[:, 1:-1],
                degree=degree - 1,
                k=k - 1,
                x=x,
                W=W2
            )


    @staticmethod
    def _bspline_get_derivative_weights(knots, degree, k, W):
        nf = knots.numel() - degree - 1
        if W is None:
            W = torch.diag(torch.ones(nf, device=knots.device, dtype=knots.dtype))
        if k == 0:
            return (degree, W)
        elif k > degree:
            return (degree, torch.zeros_like(W))
        else:
            eps = torch.tensor(1e-10, dtype=knots.dtype, device=knots.device)
            a1 = knots[:, 1:nf]
            b1 = knots[:, degree + 1 : -1]
            W2 = degree * W.diff(dim=0) / torch.maximum(b1 - a1, eps).T
            # When we write the derivative in terms of lower-degree B-splines, the
            # current formulation will contain some basis functions that have zero
            # support since their control points are just the left or right
            # endpoint repeated. So we have to remove these.
            return BSpline._bspline_get_derivative_weights(
                knots[:, 1:-1], degree - 1, k - 1, W2
            )


    def __len__(self):
        return self.degree + self.n_segments
