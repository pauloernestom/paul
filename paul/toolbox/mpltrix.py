#!/usr/bin/python

from matplotlib.collections import LineCollection
from matplotlib.gridspec import GridSpec
import paul.base.wave as wave
import numpy as np
from pprint import pprint

import logging
log = logging.getLogger(__name__)

'''
Plot tricks for matplotlib plotting
'''


def gridplot (grid, loc, rowspan=1, colspan=1):
    '''
    Returns a matplotlib.gridspec.SubplotSpec for a subplot.
    The resulting object can then be added to a matplotlib.figure
    using the add_subplot() method.
    '''
    gridspec = GridSpec (grid[0], grid[1])
    subplotspec = gridspec.new_subplotspec(loc, rowspan, colspan)
    return subplotspec


def plotwater (fig_ax, wlist, xlist=None, axis=0, offs=(0, 0), xlim=(0,0), ylim=(0,0)):
    '''
    Creates a waterfall plot on the matplotlib Axes instance
    *fig_ax* from a list of 1D waves specified by *wlist*.
    With the axis limits *xlim* and *ylim*, or auto-calculated 
    axes limits if none are specified.
    (Auto-calculated limits are quite good BTW, maybe sometimes slightly
    too large along the y-axis, depending on the data;
    mostly useful and always encompassing the whole area.)

    Returns a LineCollection object, which can be used to further
    manipulate the waterfall plot appearance.
    '''
    
    if isinstance(wlist, wave.Wave):
        return imwater(fig_ax, wlist, axis, offs, xlim, ylim, autoscale=True)

    # generate x coordinate list, if not specified
    if xlist is None:
        xlist = [np.arange(start=wave.WCast(w).dim[0].offset,
                           stop=wave.WCast(w).dim[0].end,
                           step=wave.WCast(w).dim[0].delta) for w in wlist]
    
    if xlim == (0, 0):
        xlim = (min([wave.WCast(w).dim[0].min for w in wlist]) - (offs[0]*len(wlist))*(offs[0]<0),
                max([wave.WCast(w).dim[0].max for w in wlist]) + (offs[0]*len(wlist))*(offs[0]>0))
    if ylim == (0, 0):
        ylim = (min([np.nanmin(w) for w in wlist]) + (offs[1]*len(wlist)) * (offs[1]<0),
                max([np.nanmin(w) for w in wlist]) + (offs[1]*len(wlist)) * (offs[1]>0))

    lines = LineCollection([list(zip(x, w)) for x, w in zip(xlist,wlist)], offsets=offs)

    if xlim is not None:
        fig_ax.set_xlim (xlim)
    if ylim is not None:
        fig_ax.set_ylim (ylim)

    fig_ax.add_collection (lines)
    return lines

plot_water = plotwater   # define an alias, for interface compatibility



def imwater (fig_ax, wlist, axis=0, offs=(0, 0), xlim=(0,0), ylim=(0,0), autoscale=True,
             ignore=[], scale_out={ 'offset': None, 'scale': None}):
    '''
    Same as plotwater(), but designed to work for 2D waves.
    if *autoscale* is True, then resulting line collection will have
    the same y-scaling as the original 2D wave.
    
    For a 2D wave, the X and Y axis limits are retained (i.e. a 2D
    image plot or a waterfall plot will have the same ranges).
    This is done by re-interpreting the *offs* parameter. The
    algorithm is roughly the following:
       1) Calculate the would-be y-axis span (which is 
           N * offs[y], where N is the number if 1D slices)
       2) Calculate the real y-axis span of the 2 wave
       3) Calculate the ratio between spans of (1) and (2)
       4) Scale *offs*[y] and the signal intensity by the ratio at (3).

    If specified, *ignore* is a list of line indices (in the final 'waterfall'
    line set) which to exclude from plotting.
    '''
    if len(wlist) == 0:
        return

    if len(ignore) > 0:
        err_msg = "NOT IMPLEMENTED: 'ignore' parameter!  "\
                   "(Hint: You should rather preselect input wave range.)"
        log.error (err_msg)
        raise NotImplemented (err_msg)


    if not isinstance(wlist, wave.Wave):
        new_wlist = np.vstack (wlist)  # this only works if waves have
                                       # the same number of points
        wlist = new_wlist

    # swap axes, if anything other than 0 was selected
    if axis != 0:
        print("Reversing axis")
        data = wlist.swapaxes(0, axis)
    else:
        data = wlist.copy()
        

    if len(data.shape) != 2:
        err = "Only 2D waves can be plotted as waterfalls (dim = %d here)" % len(data.shape)
        log.error (err)
        raise ValueError (err)

    ## first, calculate the X axis values
    x = np.arange(start = data.dim[1].offset,
                  stop  = data.dim[1].end,
                  step  = data.dim[1].delta)

    
    ## Do the auto-scaling magic... :-)
    
    # some indices along the y axis...
    min_i  = data.dim[0].x2i_rnd(data.dim[0].min) # index of k|| = min
    zero_i = data.dim[0].x2i_rnd(0)                # index of k|| = 0
    max_i  = data.dim[0].x2i_rnd(data.dim[0].max) # index of k|| = max
    
    # the "natural" y scaling, that would be in effect if we didn't change anything
    ylim_wouldbe = (0, data.shape[0]*offs[1] if offs[1] != 0 else (np.nanmax(data)-np.nanmin(data)))

    # the original y-range of the data
    ylim_data    = (data.dim[0].min, data.dim[0].max)

    # zoom factor from "original" to "natural" scaling
    axzoom       = (ylim_data[1]-ylim_data[0]) / (ylim_wouldbe[1]-ylim_wouldbe[0])

    # recalculate the offs parameter to have the same effect on our
    # "rescaled" data that the original parameter would have had
    # on the original data.
    offs         = (offs[0], offs[1]*axzoom)

    # Usually, LineCollection would start displaying
    # data at y=0. Here we calculate an offset we need to
    # apply to the data in order to have the lines aligned
    # at the correct position on the y axis.
    data_yshift  = -(zero_i - min_i) * abs(offs[1])

    # If we work with a negative y-offset (=offs[1]), then slices will
    # be built up the other way round (i.e. towards increasingly lower
    # y-values), meaning our data will be shown lower than
    # the original scale range. We need to shift the data one full
    # y-range to counteract that:
    if offs[1] < 0:
        data_yshift += abs(offs[1])*data.dim[0].size
                                            

    # Scale the wave intensity to have it appear as big
    # (compared to the 'offs' parameter) as it would have been
    # if we didn't interfere. Then apply the y-shifting
        
    data *= axzoom
    data += data_yshift

    # tell the calling instance what scaling parameters were
    # applied to the data -- may be important for further processing
    if scale_out is not None:
        scale_out['scale']  = axzoom
        scale_out['offset'] = data_yshift

    ## set the proper limis (only if user didn't specify his own).
    if xlim == (0, 0):
        xlim = (data.dim[1].min - (offs[0]*len(data))*(offs[0]<0),
                data.dim[1].max + (offs[0]*len(data))*(offs[0]>0))
        
    if ylim == (0, 0):
        ylim = (ylim_data[0], ylim_data[1])
        

    ## ...then go for the actual work.
    lines = LineCollection([list(zip(x, w)) for w in data], offsets=offs)

    if xlim is not None:
        fig_ax.set_xlim (xlim)
        
    if ylim is not None:
        ylim_values = (ylim[0]-(ylim[1]-ylim[0])*0.05,
                       ylim[1]+(ylim[1]-ylim[0])*0.05)

        # need to reverse display, if y-offset is negative
        if offs[1] > 0:
            fig_ax.set_ylim (ylim_values)
        else:
            fig_ax.set_ylim (ylim_values[::-1])

    fig_ax.add_collection (lines)
    return lines


