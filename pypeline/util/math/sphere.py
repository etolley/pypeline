# ##############################################################################
# sphere.py
# =========
# Author : Sepand KASHANI [sep@zurich.ibm.com]
# ##############################################################################

"""
Spherical geometry tools.
"""

import astropy.coordinates as coord
import astropy.units as u
import numpy as np

import pypeline.util.argcheck as chk
import pypeline.util.math.func as func


@chk.check('N', chk.is_integer)
def ea_sample(N):
    r"""
    Open grid of Equal-Angle sample-points on the sphere.

    Parameters
    ----------
    N : int
        Order of the grid, i.e. there will be :math:`4 (N + 1)^{2}` points on the sphere.

    Returns
    -------
    theta : :py:class:`~astropy.units.Quantity`
        (2N + 2, 1) polar angles.

    phi : :py:class:`~astropy.units.Quantity`
        (1, 2N + 2) azimuthal angles.

    Examples
    --------
    Sampling a zonal function :math:`f(r): \mathbb{S}^{2} \to \mathbb{C}` of order :math:`N` on the sphere:

    .. testsetup::

       import numpy as np
       import astropy.units as u
       from pypeline.util.math.sphere import ea_sample

    .. doctest::

       >>> N = 3
       >>> theta, phi = ea_sample(N)

       >>> np.around(theta.to_value(u.rad), 2)
       array([[0.2 ],
              [0.59],
              [0.98],
              [1.37],
              [1.77],
              [2.16],
              [2.55],
              [2.95]])
       >>> np.around(phi.to_value(u.rad), 2)
       array([[0.  , 0.79, 1.57, 2.36, 3.14, 3.93, 4.71, 5.5 ]])


    Notes
    -----
    The sample positions on the unit sphere are given (in radians) by [1]_:

    .. math::

       \theta_{q} & = \frac{\pi}{2 N + 2} \left( q + \frac{1}{2} \right), \qquad & q \in \{ 0, \ldots, 2 N + 1 \},

       \phi_{l} & = \frac{2 \pi}{2N + 2} l, \qquad & l \in \{ 0, \ldots, 2 N + 1 \}.


    .. [1] B. Rafaely, "Fundamentals of Spherical Array Processing", Springer 2015
    """
    if N <= 0:
        raise ValueError('Parameter[N] must be non-negative.')

    _2N2 = 2 * N + 2
    q, l = np.ogrid[:_2N2, :_2N2]

    theta = (np.pi / _2N2) * (0.5 + q) * u.rad
    phi = (2 * np.pi / _2N2) * l * u.rad

    return theta, phi


@chk.check(dict(q=chk.has_integers,
                l=chk.has_integers,
                f=chk.accept_any(chk.has_reals, chk.has_complex),
                N=chk.is_integer))
def ea_interp(q, l, f, N):
    r"""
    Interpolate an order-limited zonal function from Equal-Angle samples.

    Computes :math:`f(r) = \sum_{q, l} \alpha_{q} f(r_{q, l}) K_{N}(\langle r, r_{q, l} \rangle)`, where :math:`r_{q, l} \in \mathbb{S}^{2}` are points from an Equal-Angle sampling scheme, :math:`K_{N}(\cdot)` is the spherical Dirichlet kernel of order :math:`N`, and the :math:`\alpha_{q}` are scaling factors tailored to an Equal-Angle sampling scheme.

    Parameters
    ----------
    q : array-like(int)
        (N_s,) polar indices of an order-`N` Equal-Angle grid.
    l : array-like(int)
        (N_s,) azimuthal indices of an order-`N` Equal-Angle grid.
    f : array-like(float or complex)
        (N_s,) samples of the zonal function at data-points.
        :math:`L`-dimensional zonal functions are also supported by supplying an (N_s, L) array instead.
    N : int
        Order of the reconstructed zonal function.

    Returns
    -------
    :py:obj:`~typing.Callable`
        Function that outputs the value of :math:`f` at specified polar coordinates :math:`\theta, \phi`.

    Examples
    --------
    Let :math:`\gamma_{N}(r): \mathbb{S}^{2} \to \mathbb{R}` be the order-:math:`N` approximation of :math:`\gamma(r) = \delta(r - r_{0})`:

    .. math::

       \gamma_{N}(r) = \frac{N + 1}{4 \pi} \frac{P_{N + 1}(\langle r, r_{0} \rangle) - P_{N}(\langle r, r_{0} \rangle)}{\langle r, r_{0} \rangle -1}.

    As :math:`\gamma_{N}` is order-limited, it can be exactly reconstructed from it's samples on an order-:math:`N` Equal-Angle grid:

    .. testsetup::

       import numpy as np
       from pypeline.util.math.sphere import ea_sample, ea_interp, pol2cart
       from pypeline.util.math.func import sph_dirichlet

       def gammaN(r, r0, N):
           similarity = np.tensordot(r0, r, axes=1)
           d_func = sph_dirichlet(N)
           return d_func(similarity) * (N + 1) / (4 * np.pi)

    .. doctest::

       # \gammaN Parameters
       >>> N = 3
       >>> r0 = np.array([0, 0, 1])

       # Interpolate \gammaN from it's samples
       >>> theta, phi = ea_sample(N)
       >>> r = pol2cart(1, theta, phi)
       >>> g_samples = gammaN(r, r0, N)
       >>> q, l = np.meshgrid(np.arange(theta.size),
       ...                    np.arange(phi.size),
       ...                    indexing='ij')
       >>> g_interp_func = ea_interp(q.reshape(-1),
       ...                           l.reshape(-1),
       ...                           g_samples.reshape(-1),
       ...                           N)

       # Compare with exact solution at off-sample positions
       >>> theta, phi = ea_sample(2 * N)  # denser grid
       >>> g_interp = g_interp_func(theta, phi)
       >>> g_exact = gammaN(pol2cart(1, theta, phi), r0, N)
       >>> np.allclose(g_interp, g_exact)
       True

    Notes
    -----
    If :math:`f(r)` only takes non-negligeable values when :math:`r \in \mathcal{S} \subset \mathbb{S}^{2}`, then the runtime of :py:func:`~pypeline.util.math.sphere.ea_interp` can be significantly reduced by only supplying the triplets (`q`, `l`, `f`) that belong to :math:`\mathcal{S}`.
    """
    theta_sph, phi_sph = ea_sample(N)
    _2N2 = theta_sph.size

    q = np.array(q, copy=False)
    l = np.array(l, copy=False)
    if not ((q.shape == l.shape) and
            chk.has_shape((q.size,))(q)):
        raise ValueError("Parameter[q, l] must be 1D and of equal length.")
    if not all(np.all(0 <= _) and np.all(_ < _2N2) for _ in [q, l]):
        raise ValueError(f"Parameter[q, l] must contain entries in "
                         f"{{0, ..., 2N + 1}}.")

    N_s = q.size
    f = np.array(f, copy=False)
    if (f.ndim == 1) and (len(f) == N_s):
        L = 1
    elif (f.ndim == 2) and (len(f) == N_s):
        L = f.shape[1]
    else:
        raise ValueError("Parameter[f] must have shape (N_s,) or (N_s, L).")
    f = f.reshape(N_s, L)

    _2m1 = np.reshape(2 * np.r_[:N + 1] + 1, (1, N + 1))
    alpha = (np.sin(theta_sph) / _2N2 *
             np.sum(np.sin(_2m1 * theta_sph) / _2m1, axis=1, keepdims=True))
    weight = (f * alpha[q]).to_value(u.dimensionless_unscaled)

    if N <= 10:
        kernel_func = func.sph_dirichlet(N)
    else:
        kernel_func = func.sph_dirichlet(N, approx=True)

    @chk.check(dict(theta=chk.accept_any(chk.is_angle, chk.has_angles),
                    phi=chk.accept_any(chk.is_angle, chk.has_angles)))
    def interp_func(theta, phi):
        r = pol2cart(1, theta, phi)
        sh_kern = (1,) + r.shape[1:]
        sh_weight = (L,) + (1,) * len(r.shape[1:])

        f_interp = np.zeros((L,) + r.shape[1:], dtype=f.dtype)
        for w, t, p in zip(weight, theta_sph[q, 0], phi_sph[0, l]):
            similarity = np.tensordot(pol2cart(1, t, p), r, axes=[[0], [0]])
            kernel = kernel_func(similarity)

            f_interp += (kernel.reshape(sh_kern) *
                         w.reshape(sh_weight))

        return f_interp

    interp_func.__doc__ = (rf"""
        Interpolate function samples at order {N}.

        Parameters
        ----------
        theta : :py:class:`~astropy.units.Quantity`
            Polar/Zenith angle.
        phi : :py:class:`~astropy.units.Quantity`
            Longitude angle.

        Returns
        -------
        :py:class:`~numpy.ndarray`
            ({L}, ...) function values at specified coordinates.

        Examples
        --------
        N = 3
        theta, phi = ea_sample(2 * N)
        f = interp_func(theta, phi)
        """)

    return interp_func


@chk.check(dict(r=chk.accept_any(chk.is_real, chk.has_reals),
                theta=chk.accept_any(chk.is_angle, chk.has_angles),
                phi=chk.accept_any(chk.is_angle, chk.has_angles)))
def pol2eq(r, theta, phi):
    """
    Polar coordinates to Equatorial coordinates.

    Parameters
    ----------
    r : float or array-like(float)
        Radius.
    theta : :py:class:`~astropy.units.Quantity`
        Polar/Zenith angle.
    phi : :py:class:`~astropy.units.Quantity`
        Longitude angle.

    Returns
    -------
    r : :py:class:`~numpy.ndarray`
        Radius.

    theta : :py:class:`~astropy.units.Quantity`
        Elevation angle.

    phi : :py:class:`~astropy.units.Quantity`
        Longitude angle.
    """
    theta_eq = (90 * u.deg) - theta
    return r, theta_eq, phi


@chk.check(dict(r=chk.accept_any(chk.is_real, chk.has_reals),
                theta=chk.accept_any(chk.is_angle, chk.has_angles),
                phi=chk.accept_any(chk.is_angle, chk.has_angles)))
def eq2pol(r, theta, phi):
    """
    Equatorial coordinates to Polar coordinates.

    Parameters
    ----------
    r : float or array-like(float)
        Radius.
    theta : :py:class:`~astropy.units.Quantity`
        Elevation angle.
    phi : :py:class:`~astropy.units.Quantity`
        Longitude angle.

    Returns
    -------
    r : :py:class:`~numpy.ndarray`
        Radius.

    theta : :py:class:`~astropy.units.Quantity`
        Polar/Zenith angle.

    phi : :py:class:`~astropy.units.Quantity`
        Longitude angle.
    """
    theta_pol = (90 * u.deg) - theta
    return r, theta_pol, phi


@chk.check(dict(r=chk.accept_any(chk.is_real, chk.has_reals),
                theta=chk.accept_any(chk.is_angle, chk.has_angles),
                phi=chk.accept_any(chk.is_angle, chk.has_angles)))
def eq2cart(r, theta, phi):
    """
    Equatorial coordinates to Cartesian coordinates.

    Parameters
    ----------
    r : float or array-like(float)
        Radius.
    theta : :py:class:`~astropy.units.Quantity`
        Elevation angle.
    phi : :py:class:`~astropy.units.Quantity`
        Longitude angle.

    Returns
    -------
    XYZ : :py:class:`~numpy.ndarray`
        (3, ...) Cartesian XYZ coordinates.

    Examples
    --------
    .. testsetup::

       import numpy as np
       import astropy.units as u
       from pypeline.util.math.sphere import eq2cart

    .. doctest::

       >>> xyz = eq2cart(1, 0 * u.deg, 0 * u.deg)
       >>> np.around(xyz, 2)
       array([[1.],
              [0.],
              [0.]])
    """
    r = np.array([r]) if chk.is_scalar(r) else np.array(r, copy=False)
    if np.any(r < 0):
        raise ValueError("Parameter[r] must be non-negative.")

    XYZ = (coord.SphericalRepresentation(phi, theta, r)
           .to_cartesian()
           .xyz
           .to_value(u.dimensionless_unscaled))

    return XYZ


@chk.check(dict(r=chk.accept_any(chk.is_real, chk.has_reals),
                theta=chk.accept_any(chk.is_angle, chk.has_angles),
                phi=chk.accept_any(chk.is_angle, chk.has_angles)))
def pol2cart(r, theta, phi):
    """
    Polar coordinates to Cartesian coordinates.

    Parameters
    ----------
    r : float or array-like(float)
        Radius.
    theta : :py:class:`~astropy.units.Quantity`
        Polar/Zenith angle.
    phi : :py:class:`~astropy.units.Quantity`
        Longitude angle.

    Returns
    -------
    XYZ : :py:class:`~numpy.ndarray`
        (3, ...) Cartesian XYZ coordinates.

    Examples
    --------
    .. testsetup::

       import numpy as np
       import astropy.units as u
       from pypeline.util.math.sphere import pol2cart

    .. doctest::

       >>> xyz = pol2cart(1, 0 * u.deg, 0 * u.deg)
       >>> np.around(xyz, 2)
       array([[0.],
              [0.],
              [1.]])
    """
    r = np.array([r]) if chk.is_scalar(r) else np.array(r, copy=False)
    if np.any(r < 0):
        raise ValueError("Parameter[r] must be non-negative.")

    theta_eq = (90 * u.deg) - theta
    XYZ = (coord.SphericalRepresentation(phi, theta_eq, r)
           .to_cartesian()
           .xyz
           .to_value(u.dimensionless_unscaled))

    return XYZ


@chk.check(dict(x=chk.accept_any(chk.is_real, chk.has_reals),
                y=chk.accept_any(chk.is_real, chk.has_reals),
                z=chk.accept_any(chk.is_real, chk.has_reals)))
def cart2pol(x, y, z):
    """
    Cartesian coordinates to Polar coordinates.

    Parameters
    ----------
    x : float or array-like(float)
        X coordinate.
    y : float or array-like(float)
        Y coordinate.
    z : float or array-like(float)
        Z coordinate.

    Returns
    -------
    r : :py:class:`~numpy.ndarray`
        Radius.

    theta : :py:class:`~astropy.units.Quantity`
        Polar/Zenith angle.

    phi : :py:class:`~astropy.units.Quantity`
        Longitude angle.

    Examples
    --------
    .. testsetup::

       import numpy as np
       import astropy.units as u
       from pypeline.util.math.sphere import cart2pol

    .. doctest::

       >>> r, theta, phi = cart2pol(0, 1 / np.sqrt(2), 1 / np.sqrt(2))

       >>> np.around(r, 2)
       1.0

       >>> np.around(theta.to_value(u.deg), 2)
       45.0

       >>> np.around(phi.to_value(u.deg), 2)
       90.0
    """
    cart = coord.CartesianRepresentation(x, y, z)
    sph = coord.SphericalRepresentation.from_cartesian(cart)

    r = sph.distance.to_value(u.dimensionless_unscaled)
    theta = u.Quantity(90 * u.deg - sph.lat).to(u.rad)
    phi = u.Quantity(sph.lon).to(u.rad)

    return r, theta, phi


@chk.check(dict(x=chk.accept_any(chk.is_real, chk.has_reals),
                y=chk.accept_any(chk.is_real, chk.has_reals),
                z=chk.accept_any(chk.is_real, chk.has_reals)))
def cart2eq(x, y, z):
    """
    Cartesian coordinates to Equatorial coordinates.

    Parameters
    ----------
    x : float or array-like(float)
        X coordinate.
    y : float or array-like(float)
        Y coordinate.
    z : float or array-like(float)
        Z coordinate.

    Returns
    -------
    r : :py:class:`~numpy.ndarray`
        Radius.

    theta : :py:class:`~astropy.units.Quantity`
        Elevation angle.

    phi : :py:class:`~astropy.units.Quantity`
        Longitude angle.

    Examples
    --------
    .. testsetup::

       import numpy as np
       import astropy.units as u
       from pypeline.util.math.sphere import cart2eq

    .. doctest::

       >>> r, theta, phi = cart2eq(0, 1 / np.sqrt(2), 1 / np.sqrt(2))

       >>> np.around(r, 2)
       1.0

       >>> np.around(theta.to_value(u.deg), 2)
       45.0

       >>> np.around(phi.to_value(u.deg), 2)
       90.0
    """
    cart = coord.CartesianRepresentation(x, y, z)
    sph = coord.SphericalRepresentation.from_cartesian(cart)

    r = sph.distance.to_value(u.dimensionless_unscaled)
    theta = u.Quantity(sph.lat).to(u.rad)
    phi = u.Quantity(sph.lon).to(u.rad)

    return r, theta, phi