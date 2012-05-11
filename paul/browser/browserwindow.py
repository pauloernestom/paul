from PyQt4 import QtGui, QtCore

from paul.browser.ui_browserwindow import Ui_BrowserWindow

import logging
log = logging.getLogger (__name__)

class BrowserWindow (QtGui.QMainWindow, Ui_BrowserWindow):
    def __init__ (self):
        QtGui.QMainWindow.__init__(self)
        Ui_BrowserWindow.__init__(self)

        self.setupUi (self)

        # model for the file system (dir tree)
        self.fileSys = QtGui.QFileSystemModel()
        self.fileSys.setRootPath(QtCore.QDir.currentPath())
        self.fileSys.setFilter (QtCore.QDir.AllDirs | QtCore.QDir.Dirs | QtCore.QDir.Files)
        self.fileSys.setNameFilters ("*.ibw")
        self.fileSys.setNameFilterDisables (False)
        self.fileTree.setModel (self.fileSys)
        self.fileTree.activated.connect(self.dirSelected)

        # model for ibw files in the 2nd list box
        self.waveList.setRootIndex (self.fileSys.index(QtCore.QDir.currentPath()))
        self.waveList.setModel (self.fileSys)
        self.waveList.activated.connect(self.waveSelected)

        self.dirSelected (self.fileSys.index("/home/florin/local/analysis"))

    # called when user selected an entry from the dir list
    @QtCore.pyqtSlot('QModelIndex')
    def dirSelected (self, index):
        self.waveList.setRootIndex (index)
        self.fileTree.resizeColumnToContents(0)

    @QtCore.pyqtSlot('QModelIndex')
    def waveSelected (self, index):
        finfo = self.fileSys.fileInfo(index)
        fpath = self.fileSys.filePath(index)
        if finfo.isDir():
            self.waveList.setRootIndex (index)
            self.fileTree.scrollTo (index)
            self.fileTree.resizeColumnToContents(0)
        if finfo.isFile() and finfo.isReadable():
            log.info ("Loading %s" % fpath)
            self.plotCanvas.plotFile (fpath)
