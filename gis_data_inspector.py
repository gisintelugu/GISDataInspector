from qgis.PyQt.QtWidgets import QAction, QMessageBox
from .inspector_dialog import InspectorDialog
from .inspector_engine import InspectorEngine

class GISDataInspector:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.dialog = None

    def initGui(self):
        self.action = QAction("GIS Data Inspector", self.iface.mainWindow())
        self.action.setToolTip("Inspect vector layer statistics and data quality")
        self.action.triggered.connect(self.show_dialog)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("&GIS Data Inspector", self.action)

    def unload(self):
        if self.action:
            self.iface.removeToolBarIcon(self.action)
            self.iface.removePluginMenu("&GIS Data Inspector", self.action)

    def show_dialog(self):
        layer = self.iface.activeLayer()
        if not layer or layer.type() != layer.VectorLayer:
            QMessageBox.warning(self.iface.mainWindow(), "GIS Data Inspector",
                                "Please select a vector layer first.")
            return
        if self.dialog is None:
            self.dialog = InspectorDialog(self.iface.mainWindow(), layer, InspectorEngine(), self.iface)
        else:
            self.dialog.set_layer(layer)
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()
