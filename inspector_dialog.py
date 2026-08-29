from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QTextDocument
from qgis.PyQt.QtPrintSupport import QPrinter
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QComboBox,
    QCheckBox, QPushButton, QTextBrowser, QProgressBar, QMessageBox,
    QFrame, QFileDialog
)
from qgis.core import QgsProject


class InspectorDialog(QDialog):
    def __init__(self, parent=None, layer=None, engine=None, iface=None):
        super().__init__(parent)
        self.layer = layer
        self.engine = engine
        self.iface = iface

        self.setWindowTitle("GIS Data Inspector")
        self.resize(1100, 760)
        self.create_ui()
        self.populate_layers(layer)

    def create_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("GIS DATA INSPECTOR")
        title.setStyleSheet(
            "font-size:22px; font-weight:bold; padding:8px;"
        )
        layout.addWidget(title)

        subtitle = QLabel(
            "Universal GIS statistics and QA/QC dashboard"
        )
        subtitle.setStyleSheet(
            "font-size:13px; padding-bottom:8px;"
        )
        layout.addWidget(subtitle)

        # Layer selector
        form = QFormLayout()
        layer_row = QHBoxLayout()

        self.layer_combo = QComboBox()
        self.layer_combo.setMinimumHeight(32)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setMaximumWidth(90)

        layer_row.addWidget(self.layer_combo, 1)
        layer_row.addWidget(self.refresh_button)
        form.addRow("Layer:", layer_row)
        layout.addLayout(form)

        # Options
        options_frame = QFrame()
        options_layout = QHBoxLayout(options_frame)
        options_layout.setContentsMargins(0, 4, 0, 4)

        self.geometry_check = QCheckBox("Geometry Statistics")
        self.geometry_check.setChecked(True)

        self.attribute_check = QCheckBox("Attribute Statistics")
        self.attribute_check.setChecked(True)

        self.quality_check = QCheckBox("Data Quality")
        self.quality_check.setChecked(True)

        self.duplicate_check = QCheckBox("Duplicates")
        self.duplicate_check.setChecked(True)

        for widget in (
            self.geometry_check,
            self.attribute_check,
            self.quality_check,
            self.duplicate_check
        ):
            options_layout.addWidget(widget)

        options_layout.addStretch()
        layout.addWidget(options_frame)

        # Actions
        buttons = QHBoxLayout()

        self.generate_button = QPushButton("Generate Inspection")
        self.generate_button.setMinimumHeight(36)

        self.clear_button = QPushButton("Clear")
        self.clear_button.setMinimumHeight(36)

        buttons.addWidget(self.generate_button)
        buttons.addWidget(self.clear_button)
        buttons.addStretch()

        layout.addLayout(buttons)

        export_buttons = QHBoxLayout()
        export_buttons.addWidget(QLabel("Export:"))

        self.export_html_button = QPushButton("HTML")
        self.export_pdf_button = QPushButton("PDF")
        self.export_xlsx_button = QPushButton("Excel")

        self.export_html_button.setEnabled(False)
        self.export_pdf_button.setEnabled(False)
        self.export_xlsx_button.setEnabled(False)

        export_buttons.addWidget(self.export_html_button)
        export_buttons.addWidget(self.export_pdf_button)
        export_buttons.addWidget(self.export_xlsx_button)
        export_buttons.addStretch()
        layout.addLayout(export_buttons)

        self.progress = QProgressBar()
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        self.status = QLabel("Status: Ready")
        self.status.setStyleSheet("font-weight:bold;")
        layout.addWidget(self.status)

        # Dashboard results.
        self.results = QTextBrowser()
        self.results.setOpenExternalLinks(False)
        self.results.setStyleSheet(
            "QTextBrowser {"
            " background:#ffffff;"
            " color:#222222;"
            " border:1px solid #d0d0d0;"
            " padding:10px;"
            "}"
        )
        layout.addWidget(self.results, 1)

        self.generate_button.clicked.connect(self.generate_report)
        self.clear_button.clicked.connect(self.clear_report)
        self.refresh_button.clicked.connect(self.refresh_layers)
        self.layer_combo.currentIndexChanged.connect(self.layer_changed)
        self.export_html_button.clicked.connect(self.export_html)
        self.export_pdf_button.clicked.connect(self.export_pdf)
        self.export_xlsx_button.clicked.connect(self.export_xlsx)

    def populate_layers(self, preferred_layer=None):
        self.layer_combo.blockSignals(True)
        self.layer_combo.clear()

        project = QgsProject.instance()
        vector_layers = []

        for lyr in project.mapLayers().values():
            try:
                if lyr.type() == lyr.VectorLayer:
                    vector_layers.append(lyr)
            except Exception:
                pass

        preferred_index = -1

        for lyr in vector_layers:
            self.layer_combo.addItem(lyr.name(), lyr)
            if preferred_layer is not None and lyr.id() == preferred_layer.id():
                preferred_index = self.layer_combo.count() - 1

        if preferred_index >= 0:
            self.layer_combo.setCurrentIndex(preferred_index)
        elif self.layer_combo.count() > 0:
            self.layer_combo.setCurrentIndex(0)

        self.layer_combo.blockSignals(False)

        if self.layer_combo.count() == 0:
            self.layer = None
            self.status.setText("Status: No vector layers found.")
        else:
            self.layer = self.layer_combo.currentData()
            self.update_layer_info()

    def refresh_layers(self):
        current_id = self.layer.id() if self.layer else None
        preferred = None

        for lyr in QgsProject.instance().mapLayers().values():
            if lyr.id() == current_id:
                preferred = lyr
                break

        self.populate_layers(preferred)
        self.status.setText(
            f"Status: {self.layer_combo.count()} vector layer(s) available."
        )

    def set_layer(self, layer):
        self.layer = layer
        self.populate_layers(layer)

    def layer_changed(self):
        index = self.layer_combo.currentIndex()
        if index >= 0:
            selected = self.layer_combo.itemData(index)
            if selected:
                self.layer = selected
        self.update_layer_info()

    def update_layer_info(self):
        if not self.layer:
            return

        gt = self.layer.geometryType()
        name = {0: "Point", 1: "Line", 2: "Polygon"}.get(gt, "Unknown")

        self.status.setText(
            f"Status: Ready | Geometry: {name} | "
            f"Features: {self.layer.featureCount()}"
        )

    def generate_report(self):
        if not self.layer:
            QMessageBox.warning(
                self,
                "GIS Data Inspector",
                "Please select a vector layer."
            )
            return

        self.generate_button.setEnabled(False)
        self.progress.setValue(5)
        self.status.setText(
            f"Status: Inspecting '{self.layer.name()}'..."
        )

        try:
            report = self.engine.inspect(
                self.layer,
                geometry=self.geometry_check.isChecked(),
                attributes=self.attribute_check.isChecked(),
                quality=self.quality_check.isChecked(),
                duplicates=self.duplicate_check.isChecked()
            )

            self.progress.setValue(100)
            self.results.setHtml(report)
            self.export_html_button.setEnabled(True)
            self.export_pdf_button.setEnabled(True)
            self.export_xlsx_button.setEnabled(True)
            self.status.setText(
                f"Status: Inspection completed | Layer: {self.layer.name()}"
            )

        except Exception as exc:
            self.progress.setValue(0)
            self.status.setText("Status: Error")
            QMessageBox.critical(
                self,
                "GIS Data Inspector",
                f"Inspection failed:\n\n{exc}"
            )

        finally:
            self.generate_button.setEnabled(True)

    def clear_report(self):
        self.results.clear()
        self.progress.setValue(0)
        self.export_html_button.setEnabled(False)
        self.export_pdf_button.setEnabled(False)
        self.export_xlsx_button.setEnabled(False)
        self.status.setText("Status: Ready")

    def _default_export_name(self, extension):
        from datetime import datetime
        safe = "".join(
            c if c.isalnum() or c in " _-" else "_"
            for c in self.layer.name()
        ).strip().replace(" ", "_")
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"GIS_Data_Inspector_{safe}_{stamp}.{extension}"

    def export_html(self):
        if not self.layer:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export HTML Report",
            self._default_export_name("html"),
            "HTML files (*.html)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.results.toHtml())
            self.status.setText(f"Status: HTML exported — {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Export HTML", f"Export failed:\n\n{exc}")

    def export_pdf(self):
        if not self.layer:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export PDF Report",
            self._default_export_name("pdf"),
            "PDF files (*.pdf)"
        )
        if not path:
            return
        try:
            document = QTextDocument()
            document.setHtml(self.results.toHtml())
            printer = QPrinter()
            printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            printer.setOutputFileName(path)
            # Use Qt's default PDF page margins for QGIS 4 / Qt 6.
            document.print(printer)
            self.status.setText(f"Status: PDF exported — {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Export PDF", f"Export failed:\n\n{exc}")

    def export_xlsx(self):
        if not self.layer:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Excel Report",
            self._default_export_name("xlsx"),
            "Excel workbooks (*.xlsx)"
        )
        if not path:
            return
        try:
            self.engine.export_xlsx(self.layer, path)
            self.status.setText(f"Status: Excel exported — {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Excel", f"Export failed:\n\n{exc}")
