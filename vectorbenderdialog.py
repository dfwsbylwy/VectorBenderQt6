# -*- coding: utf-8 -*-
from qgis.PyQt import uic, QtWidgets
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *

from qgis.core import *
from qgis.gui import *

import os.path

from .vectorbendertransformers import *


class VectorBenderDialog(QtWidgets.QDialog):
    def __init__(self, iface, vb):
        QtWidgets.QDialog.__init__(self)
        uic.loadUi(os.path.join(os.path.dirname(__file__),'ui_main.ui'), self)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        #self.setWindowModality( Qt.WindowModality.ApplicationModal )

        self.iface = iface
        self.vb = vb

        # Keeps three rubberbands for delaunay's peview
        self.rubberBands = None

        # Connect the UI buttons
        self.createMemoryLayerButton.clicked.connect(self.createMemoryLayer)

        self.previewButton.pressed.connect(self.showPreview)
        self.previewButton.released.connect(self.hidePreview)

        self.editModeButton_toBendLayer.clicked.connect(self.toggleEditMode_toBendLayer)
        self.editModeButton_pairsLayer.clicked.connect(self.toggleEditMode_pairsLayer)

        self.runButton.clicked.connect(self.vb.run)

        # When those are changed, we recheck the requirements
        self.editModeButton_pairsLayer.clicked.connect(self.checkRequirements)
        self.editModeButton_toBendLayer.clicked.connect(self.checkRequirements)
        self.comboBox_toBendLayer.activated.connect( self.checkRequirements )
        self.pairsToPinsCheckBox.clicked.connect( self.checkRequirements )

        # When those are changed, we change the transformation type (which also checks the requirements)
        self.comboBox_toBendLayer.activated.connect( self.updateEditState_toBendLayer )
        self.comboBox_pairsLayer.activated.connect( self.updateEditState_pairsLayer )
        self.comboBox_pairsLayer.activated.connect( self.updateTransformationType )
        self.restrictBox_pairsLayer.stateChanged.connect( self.updateTransformationType )

        # Create an event filter to update on focus
        self.installEventFilter(self)


    # UI Getters
    def toBendLayer(self):
        """
        Returns the current toBend layer depending on what is choosen in the comboBox_pairsLayer
        """
        layerId = self.comboBox_toBendLayer.itemData(self.comboBox_toBendLayer.currentIndex())
        return QgsProject.instance().mapLayer(layerId)
    def pairsLayer(self):
        """
        Returns the current pairsLayer layer depending on what is choosen in the comboBox_pairsLayer
        """
        layerId = self.comboBox_pairsLayer.itemData(self.comboBox_pairsLayer.currentIndex())
        return QgsProject.instance().mapLayer(layerId)
    def bufferValue(self):
        """
        Returns the current buffer value depending on the input in the spinbox
        """
        return self.bufferSpinBox.value()

    # Updaters
    def refreshStates(self):
        """
        Updates the UI values, to be used upon opening / activating the window
        """

        # Update the comboboxes
        self.updateLayersComboboxes()

        # Update the edit mode buttons
        self.updateEditState_pairsLayer()
        self.updateEditState_toBendLayer()

        # Update the transformation type
        self.updateTransformationType()
    def checkRequirements(self):
        """
        To be run after changes have been made to the UI. It enables/disables the run button and display some messages.
        """
        # Checkin requirements
        self.runButton.setEnabled(False)

        tbl = self.toBendLayer()
        pl = self.pairsLayer()

        if tbl is None:
            self.displayMsg( u"必须先选择一个待弯曲的矢量图层！", True )
            return
        if pl is None:
            self.displayMsg( u"必须先选择一个定义点配对的矢量（线）图层！", True )
            return
        if pl is tbl:
            self.displayMsg( u"待弯曲图层不能与配对图层相同！", True )
            return            
        if not tbl.isEditable():
            self.displayMsg( u"待弯曲图层必须处于编辑状态！", True )
            return
        if not pl.isEditable() and self.pairsToPinsCheckBox.isChecked():
            self.displayMsg( u"若要将配对转为固定点，配对图层必须处于编辑状态！", True )
            return
        if self.stackedWidget.currentIndex() == 0:
            self.displayMsg(u"无效的变换类型，无法运行。", True)
            return            
        self.displayMsg(u"准备就绪，可以运行...")
        self.runButton.setEnabled(True)

    def updateLayersComboboxes(self):
        """
        Recreate the comboboxes to display existing layers.
        """
        oldBendLayer = self.toBendLayer()
        oldPairsLayer = self.pairsLayer()

        self.comboBox_toBendLayer.clear()
        self.comboBox_pairsLayer.clear()
        for layer in QgsProject.instance().mapLayers().values():
            if layer.type() == Qgis.LayerType.Vector:
                self.comboBox_toBendLayer.addItem( layer.name(), layer.id() )
                if layer.geometryType() == Qgis.GeometryType.Line:
                    self.comboBox_pairsLayer.addItem( layer.name(), layer.id() )

        if oldBendLayer is not None:
            index = self.comboBox_toBendLayer.findData(oldBendLayer.id())
            self.comboBox_toBendLayer.setCurrentIndex( index )
        if oldPairsLayer is not None:
            index = self.comboBox_pairsLayer.findData(oldPairsLayer.id())
            self.comboBox_pairsLayer.setCurrentIndex( index )
    def updateEditState_pairsLayer(self):
        """
        Update the edit state button for pairsLayer
        """
        l = self.pairsLayer()
        self.editModeButton_pairsLayer.setChecked( False if (l is None or not l.isEditable()) else True )
    def updateEditState_toBendLayer(self):
        """
        Update the edit state button for toBendLayer
        """
        l = self.toBendLayer()
        self.editModeButton_toBendLayer.setChecked( False if (l is None or not l.isEditable()) else True )
    def updateTransformationType(self):
        """
        Update the stacked widget to display the proper transformation type. Also runs checkRequirements() 
        """
        tt = self.vb.determineTransformationType()
        self.stackedWidget.setCurrentIndex( tt )

        self.checkRequirements()

    # Togglers
    def toggleEditMode(self, checked, toBendLayer_True_pairsLayer_False):
        l = self.toBendLayer() if toBendLayer_True_pairsLayer_False else self.pairsLayer()
        if l is None:
            return 

        if checked:
            l.startEditing()
        else:
            if not l.isModified():
                l.rollBack()
            else:
                retval = QMessageBox.warning(self, u"停止编辑", u"是否保存图层 %s 的更改？" % l.name(), QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Save)

                if retval == QMessageBox.StandardButton.Save:
                    l.commitChanges()
                elif retval == QMessageBox.StandardButton.Discard:
                    l.rollBack()
    def toggleEditMode_toBendLayer(self, checked):
        self.toggleEditMode(checked, True)
    def toggleEditMode_pairsLayer(self, checked):
        self.toggleEditMode(checked, False)

    # Misc
    def createMemoryLayer(self):
        """
        Creates a new memory layer to be used as pairLayer, and selects it in the ComboBox.
        """

        suffix = ""
        name = "VectorBenderQt6"
        while len( QgsProject.instance().mapLayersByName( name+suffix ) ) > 0:
            if suffix == "": suffix = " 1"
            else: suffix = " "+str(int(suffix)+1)

        newMemoryLayer = QgsVectorLayer("Linestring", name+suffix, "memory")
        # QGIS 4 (Qt6): loadNamedStyle(theURI, loadFromLocalDb, ...) -- passing False
        # keeps the historical behaviour of loading the .qml from disk only.
        newMemoryLayer.loadNamedStyle(os.path.join(os.path.dirname(__file__),'PairStyle.qml'), False)
        QgsProject.instance().addMapLayer(newMemoryLayer)

        self.updateLayersComboboxes()

        index = self.comboBox_pairsLayer.findData(newMemoryLayer.id())
        self.comboBox_pairsLayer.setCurrentIndex( index )
        
        newMemoryLayer.startEditing()  
    def displayMsg(self, msg, error=False):
        if error:
            #QApplication.beep()
            msg = "<font color='red'>"+msg+"</font>"
        self.statusLabel.setText( msg )  
    def hidePreview(self):
        if self.rubberBands is not None:
            self.rubberBands[0].reset(Qgis.GeometryType.Polygon)
            self.rubberBands[1].reset(Qgis.GeometryType.Polygon)
            self.rubberBands[2].reset(Qgis.GeometryType.Polygon)
            self.rubberBands = None
    def showPreview(self):

        self.rubberBands = (QgsRubberBand(self.iface.mapCanvas(), Qgis.GeometryType.Polygon),QgsRubberBand(self.iface.mapCanvas(), Qgis.GeometryType.Polygon),QgsRubberBand(self.iface.mapCanvas(), Qgis.GeometryType.Polygon))

        self.rubberBands[0].reset(Qgis.GeometryType.Polygon)
        self.rubberBands[1].reset(Qgis.GeometryType.Polygon)
        self.rubberBands[2].reset(Qgis.GeometryType.Polygon)

        pairsLayer = self.pairsLayer()

        transformer = BendTransformer( pairsLayer, self.restrictBox_pairsLayer.isChecked() ,self.bufferValue() )

        self.rubberBands[0].setColor(QColor(0,125,255))
        self.rubberBands[1].setColor(QColor(255,125,0))
        self.rubberBands[2].setColor(QColor(0,125,0,50))

        self.rubberBands[0].setBrushStyle(Qt.BrushStyle.Dense6Pattern)
        self.rubberBands[1].setBrushStyle(Qt.BrushStyle.Dense6Pattern)
        self.rubberBands[2].setBrushStyle(Qt.BrushStyle.NoBrush)

        self.rubberBands[0].setWidth(3)
        self.rubberBands[1].setWidth(3)
        self.rubberBands[2].setWidth(1)
      
        #draw the expanded hull
        if transformer.expandedHull is not None:
            for p in transformer.expandedHull.asPolygon()[0]:
                self.rubberBands[0].addPoint( p, True, 0  )
            for p in transformer.expandedHull.asPolygon()[0][0:1]:
                #we readd the first point since it's not possible to make true rings with rubberbands
                self.rubberBands[0].addPoint( p, True, 0  )

        #draw the hull
        for p in transformer.hull.asPolygon()[0]:
            self.rubberBands[0].addPoint( p, True, 0  ) #inner ring of rubberband 1
            self.rubberBands[1].addPoint( p, True, 0  )
        for p in transformer.hull.asPolygon()[0][0:1]:
            #we readd the first point since it's not possible to make true rings with rubberbands
            self.rubberBands[0].addPoint( p, True, 0  )

        #draw the triangles
        for i,tri in enumerate(transformer.delaunay.triangles):
            self.rubberBands[2].addPoint( transformer.pointsA[tri[0]], False, i  )
            self.rubberBands[2].addPoint( transformer.pointsA[tri[1]], False, i  )
            self.rubberBands[2].addPoint( transformer.pointsA[tri[2]], True, i  ) #TODO : this refreshes the rubber band on each triangle, it should be updated only once after this loop       

    # Events
    def eventFilter(self,object,event):
        if event.type() == QEvent.Type.WindowActivate:
            self.refreshStates()
        return False


