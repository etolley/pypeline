# #############################################################################
# spatial_domain.py
# =================
# Author : Sepand KASHANI [kashani.sepand@gmail.com]
# #############################################################################

"""
High-level Bluebild interfaces that work in the spatial domain.
"""

import numpy as np
import scipy.sparse as sparse
import time as stime

import pypeline.phased_array.bluebild.field_synthesizer.spatial_domain as ssd
import pypeline.phased_array.bluebild.imager as bim
import imot_tools.io.s2image as image
import imot_tools.util.argcheck as chk
import pypeline.util.array as array

class Spatial_IMFS_Block(bim.IntegratingMultiFieldSynthesizerBlock):
    """
    Multi-field synthesizer based on StandardSynthesis.

    Examples
    --------
    Assume we are imaging a portion of the Bootes field with LOFAR's 24 core stations.

    The short script below shows how to use :py:class:`~pypeline.phased_array.bluebild.imager.spatial_domain.Spatial_IMFS_Block` to form continuous integrated energy level estimates.

    .. testsetup::

       import numpy as np
       import astropy.units as u
       import astropy.time as atime
       import astropy.coordinates as coord
       import scipy.constants as constants
       from tqdm import tqdm as ProgressBar
       from pypeline.phased_array.bluebild.data_processor import IntensityFieldDataProcessorBlock
       from pypeline.phased_array.bluebild.imager.spatial_domain import Spatial_IMFS_Block
       from pypeline.phased_array.instrument import LofarBlock
       from pypeline.phased_array.beamforming import MatchedBeamformerBlock
       from pypeline.phased_array.bluebild.gram import GramBlock
       from pypeline.phased_array.data_gen.source import from_tgss_catalog
       from pypeline.phased_array.data_gen.statistics import VisibilityGeneratorBlock
       from imot_tools.math.sphere.grid import spherical

       np.random.seed(0)

    .. doctest::

       ### Experiment setup ================================================
       # Observation
       >>> obs_start = atime.Time(56879.54171302732, scale='utc', format='mjd')
       >>> field_center = coord.SkyCoord(218 * u.deg, 34.5 * u.deg)
       >>> field_of_view = np.deg2rad(5)
       >>> frequency = 145e6
       >>> wl = constants.speed_of_light / frequency

       # instrument
       >>> N_station = 24
       >>> dev = LofarBlock(N_station)
       >>> mb = MatchedBeamformerBlock([(_, _, field_center) for _ in range(N_station)])
       >>> gram = GramBlock()

       # Visibility generation
       >>> sky_model=from_tgss_catalog(field_center, field_of_view, N_src=10)
       >>> vis = VisibilityGeneratorBlock(sky_model,
       ...                                T=8,
       ...                                fs=196000,
       ...                                SNR=np.inf)

       ### Energy-level imaging ============================================
       # Pixel grid
       >>> px_grid = spherical(field_center.transform_to('icrs').cartesian.xyz.value,
       ...                     FoV=field_of_view,
       ...                     size=[256, 386]).reshape(3, -1)

       >>> I_dp = IntensityFieldDataProcessorBlock(N_eig=7,  # assumed obtained from IntensityFieldParameterEstimator.infer_parameters()
       ...                                         cluster_centroids=[124.927,  65.09 ,  38.589,  23.256])
       >>> I_mfs = Spatial_IMFS_Block(wl, px_grid, N_level=4)
       >>> t_img = obs_start + np.arange(20) * 400 * u.s  # well-spaced snapshots
       >>> for t in ProgressBar(t_img):
       ...     XYZ = dev(t)
       ...     W = mb(XYZ, wl)
       ...     S = vis(XYZ, W, wl)
       ...     G = gram(XYZ, W, wl)
       ...
       ...     D, V, c_idx = I_dp(S, G)
       ...
       ...     # (2, N_level, N_px) energy levels [integrated, clustered] (compact descriptor, not the same thing as [D, V]).
       ...     field_stat = I_mfs(D, V, XYZ.data, W.data, c_idx)

       >>> I_std, I_lsq = I_mfs.as_image()

    The standardized and least-squares images can then be viewed side-by-side:

    .. doctest::

       from imot_tools.io.s2image import Image
       import matplotlib.pyplot as plt

       fig, ax = plt.subplots(ncols=2)
       I_std.draw(index=slice(None),  # Collapse all energy levels
                  catalog=sky_model.xyz.T,
                  data_kwargs=dict(cmap='cubehelix'),
                  catalog_kwargs=dict(s=600),
                  ax=ax[0])
       I_lsq.draw(index=slice(None),  # Collapse all energy levels
                  catalog=sky_model.xyz.T,
                  data_kwargs=dict(cmap='cubehelix'),
                  catalog_kwargs=dict(s=600),
                  ax=ax[1])
       fig.show()

    .. image:: _img/bluebild_SpatialIMFSBlock_integrate_example.png
    """

    @chk.check(
        dict(
            wl=chk.is_real, pix_grid=chk.has_reals, N_level=chk.is_integer, precision=chk.is_integer
        )
    )
    def __init__(self, wl, pix_grid, N_level, precision=64):
        """
        Parameters
        ----------
        wl : float
            Wavelength [m] of observations.
        pix_grid : :py:class:`~numpy.ndarray`
            (3, N_px) pixel vectors.
        N_level : int
            Number of clustered energy-levels to output.
        precision : int
            Numerical accuracy of floating-point operations.

            Must be 32 or 64.
        """
        super().__init__()

        if precision == 32:
            self._fp = np.float32
            self._cp = np.complex64
        elif precision == 64:
            self._fp = np.float64
            self._cp = np.complex128
        else:
            raise ValueError("Parameter[precision] must be 32 or 64.")

        if N_level <= 0:
            raise ValueError("Parameter[N_level] must be positive.")
        self._N_level = N_level

        self._synthesizer = ssd.SpatialFieldSynthesizerBlock(wl, pix_grid, precision)
        self.timer = None

    def set_timer(self, t):
        self.timer = t
        self._synthesizer.set_timer(self.timer)

    def mark(self, tag):
      if self.timer: self.timer.start_time(tag)
    def unmark(self, tag):
      if self.timer: self.timer.end_time(tag)
    @chk.check(
        dict(
            D=chk.has_reals,
            V=chk.has_complex,
            XYZ=chk.has_reals,
            W=chk.is_instance(np.ndarray, sparse.csr_matrix, sparse.csc_matrix),
            cluster_idx=chk.has_integers,
        )
    )
    def __call__(self, D, V, XYZ, W, cluster_idx):
        """
        Compute (clustered) integrated field statistics for least-squares and standardized estimates.

        Parameters
        ----------
        D : :py:class:`~numpy.ndarray`
            (N_eig,) positive eigenvalues.
        V : :py:class:`~numpy.ndarray`
            (N_beam, N_eig) complex-valued eigenvectors.
        XYZ : :py:class:`~numpy.ndarary`
            (N_antenna, 3) Cartesian instrument geometry.

            `XYZ` must be defined in the same reference frame as `pix_grid` from :py:meth:`~pypeline.phased_array.bluebild.imager.Spatial_IMFS_Block.__init__`.
        W : :py:class:`~numpy.ndarray` or :py:class:`~scipy.sparse.csr_matrix` or :py:class:`~scipy.sparse.csc_matrix`
            (N_antenna, N_beam) synthesis beamweights.
        cluster_idx : :py:class:`~numpy.ndarray`
            (N_eig,) cluster indices of each eigenpair.

        Returns
        -------
        stat : :py:class:`~numpy.ndarray`
            (2, N_level, N_px) field statistics.
        """
        self.mark("Imager call")
        D = D.astype(self._fp, copy=False)

        self.mark("Image synthesis")
        stat_std = self._synthesizer(V, XYZ, W)
        self.unmark("Image synthesis")
        stat_lsq = stat_std * D.reshape(-1, 1, 1)
        #stat_lsq = stat_std * D.reshape(-1, 1)

        stat = np.stack([stat_std, stat_lsq], axis=0)
        self.mark("Image cluster layers")
        stat = bim.cluster_layers(stat, cluster_idx, N=self._N_level, axis=1)
        self.unmark("Image cluster layers")
        self.mark("Image update iteration")
        self._update(stat)
        self.unmark("Image update iteration")
        self.unmark("Imager call")
        return stat

    def as_image(self):
        """
        Transform integrated statistics to viewable image.

        Returns
        -------
        std : :py:class:`~imot_tools.io.s2image.Image`
            (N_level, N_px) standardized energy-levels.

        lsq : :py:class:`~imot_tools.io.s2image.Image`
            (N_level, N_px) least-squares energy-levels.
        """
        grid = self._synthesizer._grid

        stat_std = self._statistics[0]
        std = image.Image(stat_std, grid)

        stat_lsq = self._statistics[1]
        lsq = image.Image(stat_lsq, grid)

        return std, lsq


