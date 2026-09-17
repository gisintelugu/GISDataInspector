from qgis.PyQt.QtWidgets import QAction, QMessageBox
from .inspector_dialog import InspectorDialog
from .inspector_engine import InspectorEngine
from .license_manager import LicenseManager


class GISDataInspector:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.license_action = None
        self.dialog = None
        self.license_manager = LicenseManager(iface.mainWindow())

    def initGui(self):
        self.action = QAction("GIS Data Inspector", self.iface.mainWindow())
        self.action.setToolTip("Inspect vector layer statistics and data quality")
        self.action.triggered.connect(self.show_dialog)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("&GIS Data Inspector", self.action)

        self.license_action = QAction("🔐 Trial / License", self.iface.mainWindow())
        self.license_action.setToolTip("View trial status or activate a license")
        self.license_action.triggered.connect(self.show_license)
        self.iface.addPluginToMenu("&GIS Data Inspector", self.license_action)

    def unload(self):
        if self.action:
            self.iface.removeToolBarIcon(self.action)
            self.iface.removePluginMenu("&GIS Data Inspector", self.action)
        if self.license_action:
            self.iface.removePluginMenu("&GIS Data Inspector", self.license_action)

    def show_license(self):
        self.license_manager.show_license_dialog()

    def show_dialog(self):
        if not self.license_manager.require_access():
            return

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
