#!/usr/bin/python

from PyQt4 import QtGui, QtCore

from paul.viewer.viewerwindow import ViewerWindow
from paul.toolbox.widgets import ValueWidget
from paul.base.wave import Wave

import logging
log = logging.getLogger (__name__)


'''
Some base classes for wave slicing in plotscripts.
'''

class BaseSlicer:
    '''
    Base class for a slicer. SingleSlice and MultiSlice will be derived
    from this class.
    This class implements basic UI functionality, leaving for
    the sub-classes only the UI-initialization and the
    actual slicing to be done.
    For now, it GUI and functionality are merged (maybe we should
    split them?)
    Typically, slicing will be controlled by a number of values
    specified in spin boxes, to be created by the respective
    sub-classes. In order to have a snappy UI even if the
    slicing/plotting job is more work intensive, we don't trigger
    the slicing on every spin box update. Instead, on spin box updates,
    we trigger a single-shot timer with a short timeout value (~0.1 sec).
    On timeout, we do the slicing.
    This way, on single spin-box changes, the response is quick.
    On multiple changes (like auto-repeating keystrokes), only
    the last change will affect the slicing, saving lots of time.
    For this to work, it is crucial that spin boxes don't bind to
    slice(), but to triggerSlicing() instead
    '''

    def __init__(self, parent=None, axis=0, master=None, tparent=None, viewer=None):
        '''
        Parameters:
           parent:  The plotting widget parent (where the plotting widget will be shown)
           master:  Master wave (can be changed later)
           tparent: Toolbar parent, i.e. to which QMainWindow to attach
                    the toolbar to.
        '''
        
        if viewer is not None:
            self.viewer = viewer
        else:
            self.viewer = ViewerWindow (parent)
        
        if parent is not None:
            self.viewer.setParent (parent)

        self.master_wave = master  # reference to the wave we will be slicing
        self.slice_wave  = None    # the result (i.e. wave to be plotted)
        self.tools       = QtGui.QToolBar()   # subclasses should attach all UI elements here

        # the slicing timer: will be activated by triggerSlicing(),
        # will call slice() on timeout.
        self.timer = QtCore.QTimer()
        self.timer.setSingleShot (True)
        self.timer.timeout.connect(self.slice)
        
        # attach toolbar to parent, by default (or to us, if no parent)
        if tparent is None:
            self.tools_parent = self.viewer
        else:
            self.tools_parent = tparent
        self.tools_parent.addToolBarBreak()
        self.tools_parent.addToolBar(self.tools)


    def __del__(self):
        '''
        Need to remove the toolbar by hand because it might be attributed to
        a different parent window.
        '''
        log.debug ("Deleting slice for axis %d" % self.slice_axis)
        self.tools_parent.removeToolBar (self.tools)


    @QtCore.pyqtSlot()
    @QtCore.pyqtSlot(int)
    def triggerSlicing(self, val=0):
        '''
        The slicing timer. The timeout() signal is connected to self.slice().
        '''
        self.timer.start (100)  # wait 100 ms for repeated key input

        
    def _prepareMaster (self, wave):
        '''
        To be called internally, from self.slice(), when the master
        wave changes. Typically it would be used to do setup work 
        associated with the new wave (i.e. set new spinbox values...)
        '''
        self.master_wave = wave        
    Base_prepareMaster = _prepareMaster


    @QtCore.pyqtSlot()        
    def slice(self, wave=None):
        '''
        The function that does the actual slicing. Subclasses
        need to implement this.
        '''
        pass


class AxisSlicer(BaseSlicer):
    '''
    Base class for an axis-based slicer. This one typically
    slices perpendicular to a specified wave axis.
    (Opposed to a free slicer, where the the slicing takes
    place not perpendicular to a particular axis, but along
    a freely specified line.)
    '''

    def __init__ (self, parent, axis=0, master=None, tparent=None):
        '''
        Parameters are those of BaseSlicer and the following:
          axis:  Axis perpendicular to which to slice
        '''
        BaseSlicer.__init__(self, parent, master, tparent)
        self.slice_axis = axis  # axis perpendicular to which we will slice
        self.val_axis =  ValueWidget (None, "Axis: ",  QtGui.QSpinBox(),
                                      0, 99, 1, axis, self._prepareAxis)
        self.tools.addWidget(self.val_axis)


    @QtCore.pyqtSlot (int)
    def _prepareAxis (self, axis):
        ''' Make sure val_axis and slice_axis are in sync. '''
        self.slice_axis = self.val_axis.value()
        self._prepareMaster(self.master_wave)  # adjust spinbox limits
        self.slice(self.master_wave)
    Axis_prepareAxis = _prepareAxis


    def _prepareMaster(self, wave):
        self.Base_prepareMaster(wave)
        if self.master_wave is None:
            return
        self.val_axis.spin.setRange (0, self.master_wave.ndim-1)
    Axis_prepareMaster = _prepareMaster



class SingleSlicer (AxisSlicer):
    '''
    Represents an (N-1)-dim slice of an N-dimensional wave.
    '''

    # need to reimplement some methods, but we wish to retain
    # their functionality:

    def __init__(self, parent=None, axis=0, master=None, tparent=None):
        AxisSlicer.__init__(self, parent, axis, master, tparent)

        # initialize GUI
        self.val_from  = ValueWidget (None, "From: ",  QtGui.QSpinBox(), 0, 99, 1, 0,    self.triggerSlicing)
        self.val_delta = ValueWidget (None, "Delta: ", QtGui.QSpinBox(), 1, 99, 1, 1,    self.triggerSlicing)
        self.slice_label = QtGui.QLabel ("<info>")

        # attach toolbar to parent, by default (or to us, if no parent)
        for w in [ self.val_from, self.val_delta, self.slice_label ]:
            self.tools.addWidget(w)


    def _prepareMaster(self, wave):
        self.Axis_prepareMaster (wave)
        if self.master_wave is None:
            return
        self.val_from.spin.setRange (0, self.master_wave.shape[self.slice_axis])
        self.val_delta.spin.setRange (1, self.master_wave.shape[self.slice_axis])


    @QtCore.pyqtSlot()
    def slice (self, wave=None):
        # everything we do depends strongly on the selected slice_axis,
        # so if that one changes, we can aswell trigger a _prepareMaster()
        # session.
        if wave is not None:
            self._prepareMaster(wave)
        if self.master_wave is None:
            return

        xfrom = self.val_from.value()
        delta = self.val_delta.value()
        xto = xfrom + delta
        log.debug ("Slicing axis %d, from %d to %d" % (self.slice_axis, xfrom, xto))
        
        # we want to slice along an arbitrary axis, here's the strategy:
        #   . swap the axis 0 with slice_axis
        #   . slice along axis 0
        #   . swap back (slice_axis with 0)
        #   . sum along slice_axis (we want to integrate out the
        #     dimension we slice along...)
        self.slice_wave = self.master_wave.swapaxes(0,self.slice_axis)[xfrom:xto].swapaxes(self.slice_axis,0).sum(self.slice_axis)
        self.slice_label.setText(" ax%d: %5.2f : %5.2f"
                                 % (self.slice_axis,
                                    self.slice_wave.i2f(self.slice_axis, xfrom),
                                    self.slice_wave.i2f(self.slice_axis, xto)))
        self.viewer.plotWaves (self.slice_wave)



class WaterfallSlicer (AxisSlicer):
    '''
    This class generates and displays a waterfall diagram, i.e. a series
    of equally spaced 1D graphs along a given axis, from the specified
    2D image.
    The following parameters are important for a waterfall diagram:
      axis:  The slice axis
      step:  Distance between display slices
      intg:  Integration width, i.e. over how many single-step slices
             to integrate in order to generate 1 display slice

             The i-th display slice will have its intensity
             modified as follows:
             
                slice = slice*imul + i*iadd
             
      iadd:  Additional constant for intensity of display slices
             (i.e. every i-th slice will receive additonal i*iadd intensity)
      imul:  Intensity scaling to apply to every display slice.

      norm:  Normalize: if specified, the wave will be normalized
             to the maximum intensity point prior to intensity
             manipulation.
    '''
    

    def __init__ (self, parent=None, axis=0, master=None, tparent=None):
        AxisSlicer.__init__(self, parent, axis, tparent)

        self.old_intg = 1
        self.old_step = 1

        # Initialize GUI.
        self.val_step = ValueWidget (None, "Step: ",    QtGui.QSpinBox(), 1, 99, 1, 1,    self.triggerSlicing)
        self.val_intg = ValueWidget (None, "Intg.: ",   QtGui.QSpinBox(), 1, 99, 1, 1,    self.triggerSlicing)
        #self.val_iadd = ValueWidget (None, "Spacing: ", QtGui.QDoubleSpinBox(), 0, 99, 1,  0, self.triggerSlicing)
        #self.val_imul = ValueWidget (None, "Scaling: ", QtGui.QDoubleSpinBox(), 0, 99, 1,  1, self.triggerSlicing)
        self.chk_norm = QtGui.QCheckBox ("Normalize")
        self.chk_norm.stateChanged.connect (self.triggerSlicing)

        self.val_step.spin.valueChanged.connect (self.stepChanged)

        # attach toolbar to parent, by default (or to us, if no parent)
        for w in [ self.val_step, self.val_intg,
                   #self.val_iadd, self.val_imul,
                   self.chk_norm ]:
            self.tools.addWidget(w)

        # reposition the tool bar to accomodate the parmeter widgets better
        self.tools_parent.addToolBar (QtCore.Qt.LeftToolBarArea, self.tools)


    def _prepareMaster(self, wave):
        self.Axis_prepareMaster (wave)
        if self.master_wave is None:
            return
        self.val_step.spin.setRange (1, self.master_wave.shape[self.slice_axis])
        self.val_intg.spin.setRange (1, self.val_step.value())
        #for v in [ self.val_iadd, self.val_imul ]:
        #    v.spin.setRange()

    @QtCore.pyqtSlot(int)
    def stepChanged(self, step):
        '''
        Called when step value is changed by user. Intependently of the
        triggerSlicing() slot, we'll also use this slot to change the
        intg value accordingly.
        '''
        self.val_intg.spin.setRange (1, step)  # make sure that  intg <= step
        if self.old_intg == self.old_step:
            # "stick" intg and step together, if they had equal values before
            self.val_intg.spin.setValue (step)


    @QtCore.pyqtSlot()
    def slice (self, wave=None):
        if wave is not None:
            self._prepareMaster(wave)
        if self.master_wave is None:
            return

        ax = self.slice_axis
        self.old_step = step = self.val_step.value()
        self.old_intg = intg = self.val_intg.value()
        #iadd = self.val_iadd.value()
        #imul = self.val_imul.value()
        log.debug ("Waterfall along axis %d, %d slices every %d points" % (self.slice_axis, intg, step))

        new_shape = list(self.master_wave.shape)
        new_shape[ax] = self.master_wave.shape[ax] / step
        new_wave = Wave(shape=new_shape, dtype=self.master_wave.dtype)
        new_wave = 0
        
        # ignore the points that don't align well with 'step'
        max_i = new_shape[ax] * step

        for s in range(0, intg):
            # marker:  select every N-th poiunt ...but ignore bogus points at the end
            marker = [ ((((step+i-s) % step) == 0) and (i < max_i))*1 for i in range (0, self.master_wave.shape[ax]) ]
            tmp = self.master_wave.compress (marker, ax)

            norm = (1.0/intg)
            if self.chk_norm.isChecked():
                log.error ("'Normalize' is checked, but no normalization will be performed!")
                #norm /= tmp.max() # this will actually not work, because we need to
                                   # normalize every single slice by hand. basically,
                                   # if we'd really want normalized lines, we'd have
                                   # to reimplement compress() to do it.
                
            new_wave += (tmp * norm)  # ignoring iadd -- will do that at plot-time

        self.slice_wave = new_wave
        self.viewer.plotWaves (self.slice_wave)
