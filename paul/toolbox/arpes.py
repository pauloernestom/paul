#!/usr/bin/python

import logging
log = logging.getLogger (__name__)

import numpy as np
import scipy as sp
import scipy.interpolate as spi
import scipy.ndimage.interpolation as spni
import scipy.ndimage as spimg
from pprint import pprint
import paul.base.wave as w
from paul.toolbox.atrix import ncomp

from itertools import product
import pprint
import math

'''
Module with tools for analysis of Angle Resolved Photoelectron
Spectroscopy (ARPES) data.
'''


#
# Some theory and simulation helpers (related to solid state
# physics in general, or ARPES in particular: model
# dispersions, band hybridizations etc.)
#

def e(mrel=1.0, ebind=0.0, kpos=0.0, klim=1.0, pts=100, out=None):
    '''
    Returns the parabolic dispersion of an electron bound at
    energy *Ebind*, with relative mass *mrel* (1.0 being
    the mass of the free electron), centered at *kpos* momentum.
    *pts* contains the number of points in k-direction. If it's
    a single number, a 1D object wull be generated. If it's a
    tuple of at least 2 numbers, then a 2D dispersion is returned
    (i.e. a paraboloid).
    The dispersion is returned for k-values specified by *klim*.
    The semification of *klim* depends on the dimensionality
    expected. For 1D results (i.e. 1D pts value):
      1) *klim* is expected to be an iterable with 2 elements
      2) if *klim* is a single number, then (-*klim*, *klim*) is assumed
    For 2D results:
      4) *klim* is supposed to be a 2x2 iterable.
      5) if *klim* is a number, then ((-*klim*, *klim*), (-*klim*, *klim*)) is assumed
      6) if *klim* is ((nr), (nr)), then ((-nr, nr), (-nr, nr)) is assumed

    A Wave object is returned with proper intrinsic scaling. The object is
    always 2D, regardless of the user input. But if the user input requested
    a 1D wave, then the 2nd dimension will have only 1 entry.
    '''

    # Make sure 'pts' and 'klim' have sane values. We will work with
    # full 2D pts / klim layout.

    dim = 2

    # if input is 1D, add a 2nd dimension
    if not hasattr(pts, "__iter__"):
        pts = (pts, 1)
        dim = 1
    if len(pts) == 1:
        pts = (pts[0], 1)
        dim = 1

    if not hasattr(klim, "__iter__"):
        if dim == 2:
            klim = ( (min(-klim, klim), max(-klim, klim)),
                     (min(-klim, klim), max(-klim, klim)) )
        else:
            klim = ( (min(-klim, klim), max(-klim, klim)),
                     (0.0, 0.0))

    else:
        new_klim = []
        if dim == 2:
            for l in klim:
                if not hasattr(l, "__iter__") or len(l) == 1:
                    new_klim.append ( (min(-l, l),
                                       max(-l, l)) )
                else:
                    new_klim.append (tuple(l))
        elif dim == 1:
            new_klim = [klim, (0.0, 0.0)]
        klim = tuple(new_klim)

    # these are the X and Y axes arrays (1D)
    axx = sp.linspace(klim[0][0], klim[0][1], pts[0])
    axy = sp.linspace(klim[1][0], klim[1][1], pts[1])
    kx = axx[:,np.newaxis]
    ky = axy[np.newaxis,:]

    #print ("axx: %s, axy: %s\nklim=%s, pts=%s" % (axx, axy, klim, pts))

    me   = 9.10938215e-31        # free electron mass [kg]
    hbar = 1.054571628e-34       # in    [kg m^2 / s]
    eV   = 1.60217646e-19        # conversion factor J -> eV [kg m^2 / s^2]

    out = ebind + 1.0/eV * (( (kx**2+ky**2) - (kpos**2))*1.0e20) * (hbar**2.0) / (2.0*mrel*me)

    if type(out) is w.Wave:
        wav = out
    else:
        wav = out.view(w.Wave)

    for i in range(len(wav.shape)):
       wav.setLimits (i, klim[i][0], klim[i][1])

    return wav


def hybridize(wlist, V=0.0, count=1):
    '''
    --------------------------------------------------------------
    ACHTUNG: This implementation is broken, gives too high gaps
             (by a factor of somewhere around ~2).
             Besides, this implementation is not physically
             sound (although the results, apart from the
             wrong factor, seem plausible).
             A physically correct implementation would
             involve constructing a Hamiltonian matrix
             with the bands on the diagonals and the
             interaction potentials off-diagonal, and
             diagonalizing that matrix in order to gain
             the hybridized bands.
    --------------------------------------------------------------
    
    Hybridizes bands from *wlist* using the coupling matrix *V*.
    *V* is a NxN matrix, where N = len(wlist).
    Returns a list hybridized bands, corresponding to:

       hi/hj = 1/2 * (wlist[i] + wlist[j] +/- sqrt((wlist[i]-wlist[j])**2 + 4*abs(v)))

    If *count* is specified, then the procedure will be repeated *count*
    times (default is 1). This is intended for multi-band hybridization,
    where one pass may not be enough.
    '''
    # if only one value is specified, construct a coupling matrix out of it
    if type(V) == float:
        V = np.matrix([[V for i in wlist] for j in wlist]) / 2

    V -= np.diag(np.diag(V))

    V2  = V + V.T - 2*np.diag(np.diag(V))      # make sure matrix is symmetric
    V2 -= np.diag(np.diag(V))                  # remove diagonal elements

    ''' This is what we'll be operating on'''
    hlist = list(wlist)
    
    '''
    Hybridizing bands more than once brings some normalization problems:
    the interaction potential V will be applied to the complete band.
    The formula has most drastic consequences for the crossover-points,
    but it actually affects the _whole_ band. Now, if we repeatedly
    hybridize two bands, then they will get pushed appart, even if they
    don't cross anymore.
    
    To avoid this, we need to normalize the interaction potential by the
    number of times that we're going to hybridize. (Mind the sqrt() -- this
    is because the potential needs to be halvened under the sqrt().)
    '''
    norm = 1.0/np.sqrt(count)

    '''
    Next problem arises when hybridizing more than 2 bands: multi-band
    hybridization is performet in a each-with-every-other kind of loop.
    So, we need to keep the interaction potential even smaller.
    The (missing) factor 1/2 accounts for the fact that our algorithm,
    for symmetry reasons, would hybridize a i->j and j->i.
    There is no sqrt() here, because this normalization factor is
    '''
    norm *= 1.0/(len(wlist)*(len(wlist)-1)/2.0)

    
    V2 *= norm  # The actual normalization

    '''
    Now, V2 is a traceless, symmetric matrix containing coupling
    factors for the bands in 'hlist', correctly normalized. Let's go!
    '''
    for t in range(count):
        for i in range(len(hlist)):
            for j in range(len(hlist)):
                if i == j:
                    continue
                h1 = 0.5 * (hlist[i] + hlist[j]) + \
                    np.sqrt( (0.5*(hlist[j]-hlist[i]))**2 + V2[i,j]**2 )
                h2 = 0.5 * (hlist[i] + hlist[j]) - \
                    np.sqrt( (0.5*(hlist[j]-hlist[i]))**2 + V2[i,j]**2 )
                hlist[i] = h1
                hlist[j] = h2

    return hlist


#
# Data manipulation helpers (normalization, coordinate transformation etc)
#

def norm_by_noise (data, axis=0, xpos=(None, None), ipos=(None, None),
                   copy=True, smooth=None, stype='gauss', field=False):
    '''
    Normalizes 1D sub-arrays obtained from a N-dimensional ndarray
    along *axis* by the values integrated along
    *axis* in range specified by *pos*.
    
    In ARPES, this is a useful feature for normalizing    
    spectra obtained in a synchrotron facility, which usually
    have significant amount of 2nd-order intensity above
    the Fermi level. Usually, *dim* would be set to represent
    the energy axis, and *pos* should be set to a range
    well above the Fermi level.

    

    Parameters:
      - *data* is the (multi-dimensional) ndarray containing
        the data. Data poins _will be modified_, so be sure to
        operate on a copy if you wish to retain original data.
        If the data has more than 2 dimensions, the array
        is rotated such that *dim* becomes the last axis, and
        norm_by_noise() iterated on all elements of data,
        recursively until dimension is 2.
    
      - *ipos* is expected to be a tuple containing a
        (from, to) value pair in 
        If *ipos* is 'None', a background auto-detection is
        attempted using gnd_autodetect().
        If *ipos* is a tuple, but either of the *ipos* elements
        is None, the element is replaced by the beginning
        or ending index, respectively.

      - *xpos* same as *ipos*, only positions are specified
        in axis coordinates of the axis specified by *dim*.
        If present, *xpos* takes precedent over *ipos*.

      - *axis* is the axis representing the array to be, i.e.
        the one to be normalized.

      - *copy* if True (the default), then the normalization will
        be performed on a copy of the original array, the original
        data remaining unchanged. Otherwise the original array
        will be modified.

      - *smooth*: Smoothing factor to apply to the data. Can
        be either None (default), 'auto', a number, or an
        (N-1) long tuple of numbers. If it's a tuple, one
        number per dimension is assumed.
        See also: PRO TIP below.

        The meaning of *smooth* depends on the parameter *stype*
        *stype* == 'spline':
          The number is the factor by which the intensity field
          is down-sampled for smoothing (smoothing is done by
          up-sampling the intensity field again to its original value,
          once it has been down-sampled).
          If it is 'auto', for each dimension the proper factor
          is guesst such that after downsampling, approximately
          40 ('ish :-) data points remain.
          None (the default) means no intensity smoothing.
          Down- and up-sampling are performed using 3rd degree
          splines from (scipy.ndimage.map_coordinates).
          Produces polinomial artefacts if intensity distribution
          is very uneven, or data is very noisy.

        *stype* == 'gauss': Smooting is done by a convolution
          of the intensity map with an (N-1)-dimensional Gauss
          profile. In that case, *smooth* contains the Sigma
          parameters of the Gaussian in each dimension.
          Produces artefacts at the border of the image.

      - *stype*: smooth type, either one of 'spline' or 'gaussian'.
        Specifies the type of smoothing.

      - *field*: if True, then the smooth field in original,
        in its down-, and its up-sampled version will also be
        returned (useful for debugging and data quality
        estimates). See also: PRO TIP below.
        
        
        PRO TIP: intensity smoothing can create very strange
        artefacts when dealing with low-intensity / noisy data!
        In that case, either go with the default (i.e. no
        smoothing -- the eye does a better job of "smoothing"
        noisy data anyway), or enable the *field* option and
        _check_ _your_ _normalization_ _fields_ _manually_! ;-)
        In most cases, gaussian smoothing works best with
        experimental data, i.e. produces the most predictible
        amount of artefacts.
        
    '''

    # rotate axes such that dim is the first
    _data = data.swapaxes(0, axis)

    # we'll be working on Waves all along -- this is
    # because we want to retain axis scaling information
    if copy == True:
        data2 = _data.copy(w.Wave)
    else:
        data2 = _data.view(w.Wave)
        data2.setflags(write=True)

    # translate everything to index coordinates,
    # xpos has precedence over ipos
    index = [data2.dim[0].x2i_rnd(x) if x is not None
             else i if i is not None
             else f
             for x, i, f in zip(xpos, ipos, (0, data2.shape[0]-1))]

    # Calculate (N-1)-dim normalization values field. Note that the field
    # itself will be normalized by the number of composing elements along
    # axis. This way, the normalized area will be, by definition, roughly ~1.0
    # Later we can substract 1.0 from the data to have a well defined zero-level :-)
    _norm_field   = data2[index[0]:index[1]].sum(0) / (index[1]-index[0])

    if smooth is not None and stype == 'spline':
        # Smoothing "hack": resample the intensity map twice:
        #  a) first to lower resolution (1/smooth), to get rid of noise
        #  b) then back to original resolution (a * smooth), to get the
        #     proper size again.
        # Use splines for down- and up-sampling, so as little information
        # gets lost as possible

        # a decent estimate: use something like 40(-ish) points per dimension,
        if smooth == 'auto':
            smooth = (np.array(_norm_field.shape) / 40).astype('int') + 3

        # smooth is interpreted as an (N-1)-dim tuple specifying for
        # each dimension the step size (in data points) of smoothing).
        if not hasattr(smooth, "__len__"):
            smooth = np.array([smooth] * _norm_field.ndim)
        else:
            smooth = np.array(smooth)
            if _norm_field.ndim != len(smooth):
                raise ValueError ("Need a smoothing tuple of length %d for an %d-dim array." 
                                  % (_norm_field.ndim))

                
        
        # down-sampling
        _cmp_coord = np.indices((np.array(_norm_field.shape)/smooth) + np.ones(smooth.shape))
        for i, s in zip (_cmp_coord, smooth):
            i *= s
        _cmp_field = spni.map_coordinates (_norm_field, _cmp_coord,
                                           order=3, mode='nearest')[np.newaxis]
            
        # up-sampling (expand again to original size)
        _smooth_coord = np.indices(_norm_field.shape).astype('float32')
        for i, s in zip (_smooth_coord, smooth):
            i /= s
        _smooth_field = spni.map_coordinates (_cmp_field[0], _smooth_coord,
                                              order=3, mode='nearest')

        ## Apply correct scaling to _smooth_field and _tmp_field
        ## (this is just for debugging purposes).
        #b = _cmp_field.view(w.Wave)
        #for d1, d0, s in zip(b.dim[1:], _norm_field.dim, smooth):
        #    d1.offset = d0.offset
        #    d1.delta = d0.delta * float(s)
        #_cmp_field = b

    elif smooth is not None and stype == 'gauss':

        # auto-select smooth parameter:
        # sigma somewhere close to 1%
        # (i.e. FWHM somewhere at ~2.4%)
        if smooth == 'auto':
            smooth = [] 
            for d in _norm_field.shape:
                sigma = math.floor(float(d)/100.0)
                smooth.append (sigma)
        _smooth_field = spimg.filters.gaussian_filter (_norm_field, smooth)


    else:
        _smooth_field = _norm_field
        
    
    data2 /= np.abs(_smooth_field[np.newaxis])
    data2 -= 1.0

    if field:         # for debugging of code and data... ;-)
        _smooth_wave = _smooth_field.view(w.Wave)
        for d1,d0 in zip(_smooth_wave.dim[1:], _norm_field.dim):
            d1.lim = d0.lim
        return data2.swapaxes(axis, 0), _norm_field, _smooth_wave

    else:
        return data2.swapaxes(axis, 0)


def get_ref2d_profile (refdata, axis=0, steps=None, width=None, ipos=None, xpos=None):
    '''
    Returns the intensity profile of the spectrum and returns a smoothened
    version of the intensity profile.

    Parameters:
      - refdata: The 2D reference data (ndarray or Wave)
      - axis:    Axis along which to build the profile
                 (the resulting profile will have length=shape[axis].
      - ipos:    Indices along (not axis) between which to integrate.
      - xpos:    Same as *ipos*, only positions are specified in axis
                 coordinates. Works only if input is a Wave(), takes
                 precedence over *ipos* if both are specified.
      - steps:   Number of steps to sustain the profile while spline-
                 smoothing. Must be smaller than shape[axis].
                 The smaller the number, the more drastic the smoothing.
                 None is aequivalent to *step* of shape[axis] means no
                 smoothing at all.
      - width:   Alternative way of specifying the smoothing. Reduces
                 data resolution in (not *axis*) direction by the factor
                 1/*width* by integrating over *width* values, then
                 interpolates the missing values using splines.
    
    Retuns: an 1D 
    '''

    if refdata.ndim != 2:
        raise ValueError ("Wrong dimension %d, expecting 2D data." % refdata.ndim)

    ref = refdata.swapaxes(0,axis)
    
    if xpos is not None:
        if not isinstance (refdata, w.Wave):
            raise ValueError ("Expecting 'Wave' container with parameter 'xpos'.")
        ipos = (ref.dim[0].x2i(xpos[0]), ref.dim[0].x2i(xpos[1]))

    if ipos is None:
        ipos = (0, ref.shape[1])

    #
    # smoothing will be done by reshaping the array
    #
    if steps is None:
        steps = ref.shape[1]
    width = math.floor(ref.shape[1] / steps)

    _tmp = ref[ipos[0]:ipos[1]].sum(0)[0:steps*width].view(np.ndarray)
    _xin  = np.arange(len(_tmp))
    _xout = np.arange(ref.shape[1])


    # output data -- copying to retain Wave() information
    out = ref[0].copy()

    #print width, steps, width*steps, _xout.shape
    #print _xin.reshape((width,steps)).sum(0).shape
    #print _xin.shape, _xout.shape
    #print _xin[::width]
    #return  _xin[::width], _tmp.reshape((steps,width)).sum(1)/width

    out[:] = spi.UnivariateSpline (_xin[::width],
                                   _tmp.reshape((steps,width)).sum(1)/width)(_xout)[:]

    return out
    


def deg2k (*args, **kwargs):
    '''
    Converts a Wave from the natural coordinates of an ARPES
    measurement (energy / degrees) into k-space (inverse space)
    coordinates.

    Following parametes:
      - (unnamed):    The 3D data, either as a Wave or as an ndarray,
                      containing the deg_tilt*deg_detector*E dependent data
                      (i.e. the intensity in dependence of energy, the tilt
                      angle, and the detector angle). If data is a Wave,
                      axis information is extracted from the wave scaling.
                      'e', 'd' and 't' parameters below override internal
                      Wave data. If data is an ndarray, then 'e', 'd' and 't'
                      parameters are mandatory.
      - axes:         Combination of the letters 'e', 'd' and 't'
                      describing the current axes layout
                      in terms of (e)nergy, (d)etector or (t)ilt.
                      Default is 'edt'.
      - energy, e:    Values to go along with the energy axis.
      - detector, d:  Values for the detector axis.
      - tilt, t:      Values for the tilt axis.
      - hv            The photon energy at which the data was measured.
      - degree:       The spline degree to use for interpolation.
                      Default is 3.
      
    '''

    # Strategy:
    #  . create a new data view
    #  . tilt data such that axes configuration
    #    is (energy, detector, tilt)
    #  . apply corrections (offsets, and possibly increments)
    #  . ...


    # parameter helpers
    _param = lambda k0, k1, d: \
      kwargs[k0] if kwargs.has_key(k0) \
      else (kwargs[k1] if kwargs.has_key(k1) else d)

    if args[0].ndim != 3:
        raise ValueError ("Input has to be a 3D array of values. "
                          "Use numpy.newaxis for proper casting of 2D arrays!")

    # rotate data into 'edt' axis configuration
    axes = kwargs.setdefault('axes', 'edt')
    idata = w.transpose(args[0], (axes.find('e'), axes.find('d'), axes.find('t')))
    
    E      = _param ('energy',   'e', idata.dim[0].range)
    ideg_d = _param ('detector', 'd', idata.dim[1].range)
    ideg_t = _param ('tilt',     't', idata.dim[2].range)
    hv     = _param ('hv',       'hv', 1.0)
    fill   = _param ('fill',     'fill', np.nan)
    degree = _param ('degree',   'deg', 3)
    _out = idata.copy()

    c     = 0.51232 * math.sqrt(hv)
    _d2k = lambda deg:  c*np.sin(deg*np.pi/180.0)

    # axes limits of the k-space data
    ik_d_lim = _d2k (np.array([ideg_d[0], ideg_d[-1]]))
    ik_t_lim = _d2k (np.array([ideg_t[0], ideg_t[-1]]))

    # rectangular, evenly-spaced grid in k coordinates;
    kaxis_d = np.linspace (start=ik_d_lim[0], stop=ik_d_lim[1], num=len(ideg_d))
    kaxis_t = np.linspace (start=ik_t_lim[0], stop=ik_t_lim[1], num=len(ideg_t))

    # for some funny reason, we need to invert det/tilt order here...
    okt, okd = np.meshgrid(kaxis_t, kaxis_d)

    # Polar coordinates for the rectangular k-space grid.
    # These will _not_ be rectangular, and they will not be on
    # a grid. Basically, this is where the magic happens:
    #   after we calculate the would-be polar coordinates
    #   of the target rectangular k-space grid, we'll use
    #   a fast spline interpolation to get data from the
    #   original polar-grid onto the new,
    #   k-space grid (represented as polar non-grid).
    #
    # Everything else is just house keeping. :-)
    #
    odeg_d = np.arcsin (okd / c) * 180.0/np.pi
    odeg_t = np.arcsin (okt / (c*np.cos(np.arcsin(okd/c))) ) * 180.0/np.pi

    # Some of the coordinates above may end up as NaNs (depending
    # on angle combination). As the interpolator will choke on NaN
    # coordinates, we need to replace them by sane numbers before
    # evaluation, and delete them again after evaluation.
    nan_map = np.isnan(odeg_d) + np.isnan(odeg_t)    # map of the NaN values
    odeg_d_clean = odeg_d.copy()
    odeg_t_clean = odeg_t.copy()
    odeg_d_clean[nan_map] = ideg_d[0] # safe polar non-grid to...
    odeg_t_clean[nan_map] = ideg_t[0] # ...use with the interpolator.

    for idat, odat in zip(idata, _out):
        #_in_masked = np.ma.masked_invalid (idat)        
        _inter = sp.interpolate.RectBivariateSpline (ideg_d, ideg_t, idat,
                                                     kx=degree, ky=degree)
        _tmp = _inter.ev(odeg_d_clean.flat, odeg_t_clean.flat)

        #print "shapes:", ideg_d.shape, ideg_t.shape, idat.shape
        #_inter = spi.interp2d (ideg_d, ideg_t, idat)
        #_tmp = _inter (odeg_d_clean.flat, odeg_t_clean.flat)

        _tmp[nan_map.flat.copy()] = fill
        _tmp2 = _tmp.reshape ([odeg_d.shape[0], odeg_t.shape[1]])
        odat[:,:] = _tmp2[:,:]

    
    if isinstance (idata, w.Wave):
        odata = _out.view(w.Wave)
        odata.dim[1].lim = ik_d_lim
        odata.dim[2].lim = ik_t_lim
    else:
        odata = _out
    
    return odata
    


if __name__ == "__main__":

    log = logging.getLogger ("paul")

    fmt = logging.Formatter('%(levelname)s: %(funcName)s: %(message)s')
    ch  = logging.StreamHandler()
    ch.setFormatter(fmt)
    ch.setLevel (logging.DEBUG)
    log.addHandler (ch)
    log.setLevel (logging.DEBUG)

    #foo = e(pts=(5, 4), mrel=-2)
    #foo = e()
    #pprint (foo)
    #print foo.info['axes']
    #e(pts=5, klim=1.0)
    #e(pts=5, llim=(-1.0, 0.5))
    #e(pts=(4, 5), klim=((1.0), (1,0)))
