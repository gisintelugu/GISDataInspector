import re
import hashlib
import math
import zipfile
from collections import Counter
from qgis.core import QgsWkbTypes, QgsDistanceArea
from qgis.PyQt.QtCore import QMetaType

class InspectorEngine:
    def __init__(self):
        self.control_pattern = re.compile(r"[\\x00-\\x08\\x0B\\x0C\\x0E-\\x1F\\x7F]")
        self.edge_pattern = re.compile(r"^[\\s,.;:|/\\\\@#$%^&*+=!?_-]+|[\\s,.;:|/\\\\@#$%^&*+=!?_-]+$")
        self.multi_space_pattern = re.compile(r" {2,}")

    def _qa_dashboard_counts(self, layer):
        total = layer.featureCount()
        invalid = 0
        empty = 0
        multipart = 0
        zero_geom = 0

        for f in layer.getFeatures():
            if not f.hasGeometry():
                empty += 1
                continue
            g = f.geometry()
            if g is None or g.isEmpty():
                empty += 1
                continue
            try:
                if not g.isGeosValid():
                    invalid += 1
            except Exception:
                pass
            try:
                if g.isMultipart():
                    multipart += 1
            except Exception:
                pass
            try:
                gt = layer.geometryType()
                if gt == QgsWkbTypes.PolygonGeometry and g.area() <= 0:
                    zero_geom += 1
                elif gt == QgsWkbTypes.LineGeometry and g.length() <= 0:
                    zero_geom += 1
            except Exception:
                pass

        return {
            "total": total,
            "invalid": invalid,
            "empty": empty,
            "multipart": multipart,
            "zero_geom": zero_geom
        }

    def _dashboard_badge(self, status):
        if status == "PASS":
            return "<span style='background:#16a34a;color:white;padding:3px 8px;border-radius:10px;font-weight:bold;'>PASS</span>"
        if status == "WARNING":
            return "<span style='background:#f59e0b;color:white;padding:3px 8px;border-radius:10px;font-weight:bold;'>WARNING</span>"
        return "<span style='background:#dc2626;color:white;padding:3px 8px;border-radius:10px;font-weight:bold;'>ERROR</span>"

    def _dashboard_status(self, count, total):
        if count == 0:
            return "PASS"
        rate = (count / max(total, 1)) * 100.0
        return "WARNING" if rate <= 1.0 else "ERROR"

    def _dashboard_score(self, qa):
        total = max(qa["total"], 1)
        penalty = (
            min((qa["invalid"] / total) * 45.0, 45.0) +
            min((qa["empty"] / total) * 25.0, 25.0) +
            min((qa["multipart"] / total) * 10.0, 10.0) +
            min((qa["zero_geom"] / total) * 20.0, 20.0)
        )
        return max(0.0, 100.0 - penalty)

    def export_xlsx(self, layer, path):
        """Export a structured Excel-compatible XLSX QA/QC report."""
        from datetime import datetime

        def col_letter(n):
            result = ""
            while n:
                n, rem = divmod(n - 1, 26)
                result = chr(65 + rem) + result
            return result

        def esc(value):
            value = "" if value is None else str(value)
            return (value.replace("&", "&amp;")
                         .replace("<", "&lt;")
                         .replace(">", "&gt;")
                         .replace('"', "&quot;")
                         .replace("'", "&apos;"))

        def make_sheet(rows):
            xml = [
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
                '<sheetData>'
            ]
            for ri, row in enumerate(rows, 1):
                xml.append(f'<row r="{ri}">')
                for ci, value in enumerate(row, 1):
                    ref = f"{col_letter(ci)}{ri}"
                    xml.append(
                        f'<c r="{ref}" t="inlineStr">'
                        f'<is><t>{esc(value)}</t></is></c>'
                    )
                xml.append("</row>")
            xml.append("</sheetData></worksheet>")
            return "".join(xml)

        typ = self.geometry_name(layer)
        qa = self._qa_dashboard_counts(layer)
        score = self._dashboard_score(qa)

        def status(count):
            if count == 0:
                return "PASS"
            rate = count / max(qa["total"], 1)
            return "WARNING" if rate <= 0.01 else "ERROR"

        dashboard = [
            ["GIS Data Inspector - QA/QC Report"],
            ["Generated", datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
            ["Layer", layer.name()],
            ["Geometry Type", typ],
            ["Feature Count", layer.featureCount()],
            ["Field Count", len(layer.fields())],
            ["CRS", layer.crs().authid() or "Custom CRS"],
            ["QA Score", f"{score:.1f}/100"],
            [],
            ["QA/QC Check", "Count", "Status"],
            ["Invalid geometries", qa["invalid"], status(qa["invalid"])],
            ["Empty / missing geometries", qa["empty"], status(qa["empty"])],
            ["Multipart geometries", qa["multipart"], status(qa["multipart"])],
            ["Zero-area / zero-length", qa["zero_geom"], status(qa["zero_geom"])]
        ]

        fields = [
            ["Field", "Type", "Unique Count", "Null / Empty",
             "Duplicate Values", "Suspicious Values"]
        ]
        features = list(layer.getFeatures())

        for fld in layer.fields():
            vals = [f[fld.name()] for f in features]
            nonempty = [v for v in vals if v is not None and str(v).strip() != ""]
            counts = {}
            suspicious = 0
            for v in nonempty:
                key = str(v)
                counts[key] = counts.get(key, 0) + 1
                if isinstance(v, str):
                    if v != v.strip() or any(ord(ch) < 32 for ch in v):
                        suspicious += 1

            fields.append([
                fld.name(),
                fld.typeName(),
                len(set(str(v) for v in nonempty)),
                len(vals) - len(nonempty),
                sum(1 for c in counts.values() if c > 1),
                suspicious
            ])

        feature_rows = [["FID"] + [f.name() for f in layer.fields()]]
        for f in features:
            row = [f.id()]
            for fld in layer.fields():
                value = f[fld.name()]
                row.append("" if value is None else value)
            feature_rows.append(row)

        content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/worksheets/sheet3.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>"""

        root_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""

        workbook = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets>
<sheet name="Dashboard" sheetId="1" r:id="rId1"/>
<sheet name="Field Statistics" sheetId="2" r:id="rId2"/>
<sheet name="Features" sheetId="3" r:id="rId3"/>
</sheets></workbook>"""

        workbook_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet3.xml"/>
</Relationships>"""

        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as out:
            out.writestr("[Content_Types].xml", content_types)
            out.writestr("_rels/.rels", root_rels)
            out.writestr("xl/workbook.xml", workbook)
            out.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
            out.writestr("xl/worksheets/sheet1.xml", make_sheet(dashboard))
            out.writestr("xl/worksheets/sheet2.xml", make_sheet(fields))
            out.writestr("xl/worksheets/sheet3.xml", make_sheet(feature_rows))

    def inspect(self, layer, geometry=True, attributes=True, quality=True, duplicates=True):
        r = []

        typ = self.geometry_name(layer)
        qa = self._qa_dashboard_counts(layer)
        score = self._dashboard_score(qa)

        if score >= 95:
            score_status = "PASS"
        elif score >= 80:
            score_status = "WARNING"
        else:
            score_status = "ERROR"

        r.append("""
<style>
body{font-family:Arial,sans-serif;color:#222;background:#fff;}
h1,h2,h3,h4,p,div,span,td,th,b,strong{color:#222;}
.dashboard-title{font-size:24px;font-weight:bold;color:#111827;margin:5px 0;}
.dashboard-sub{font-size:13px;color:#6b7280;margin-bottom:14px;}
.cards{width:100%;border:0;}
.cards td{border:0;padding:5px;}
.card{border:1px solid #d1d5db;background:#f8fafc;padding:12px;}
.card-label{font-size:11px;color:#6b7280;text-transform:uppercase;}
.card-value{font-size:22px;font-weight:bold;color:#111827;margin-top:4px;}
.section-title{font-size:17px;font-weight:bold;color:#111827;margin-top:20px;}
table.report{width:100%;border-collapse:collapse;margin-top:7px;}
table.report th{background:#eef2f7;color:#111827;padding:7px;border:1px solid #d1d5db;text-align:left;}
table.report td{background:#fff;color:#222;padding:7px;border:1px solid #d1d5db;}
.note{font-size:12px;color:#6b7280;}
</style>
""")

        r.append("<div class='dashboard-title'>GIS DATA INSPECTOR — QA/QC DASHBOARD</div>")
        r.append(
            f"<div class='dashboard-sub'><b>{self.esc(layer.name())}</b> "
            f"• {typ} • {self.esc(layer.crs().authid() or 'Custom CRS')}</div>"
        )

        r.append("<table class='cards'><tr>")
        r.append(
            f"<td><div class='card'><div class='card-label'>Feature Count</div>"
            f"<div class='card-value'>{qa['total']:,}</div></div></td>"
        )
        r.append(
            f"<td><div class='card'><div class='card-label'>Field Count</div>"
            f"<div class='card-value'>{len(layer.fields()):,}</div></div></td>"
        )
        r.append(
            f"<td><div class='card'><div class='card-label'>Geometry</div>"
            f"<div class='card-value'>{typ}</div></div></td>"
        )
        r.append(
            f"<td><div class='card'><div class='card-label'>QA Score</div>"
            f"<div class='card-value'>{score:.1f}/100</div>"
            f"<div>{self._dashboard_badge(score_status)}</div></div></td>"
        )
        r.append("</tr></table>")

        r.append("<div class='section-title'>QA/QC SUMMARY</div>")
        r.append("<table class='report'>")
        r.append("<tr><th>Check</th><th>Count</th><th>Status</th><th>Meaning</th></tr>")

        qa_checks = [
            ("Invalid geometries", qa["invalid"], "Geometry fails validity test"),
            ("Empty / missing geometries", qa["empty"], "Feature has no usable geometry"),
            ("Multipart geometries", qa["multipart"], "Feature contains multiple parts"),
            ("Zero-area / zero-length", qa["zero_geom"], "Potential geometry issue"),
        ]

        for label, count, meaning in qa_checks:
            status = self._dashboard_status(count, qa["total"])
            r.append(
                f"<tr><td>{label}</td><td>{count:,}</td>"
                f"<td>{self._dashboard_badge(status)}</td><td>{meaning}</td></tr>"
            )

        r.append("</table>")
        r.append(
            "<p class='note'>PASS = no issue detected. WARNING = low-rate issue. "
            "ERROR = issue rate above the preliminary warning threshold. "
            "Review project-specific QA/QC rules before accepting the score.</p>"
        )

        r.append("<div class='section-title'>DETAILED INSPECTION</div>")
        r.append("<h2>1. Layer Summary</h2><table border='1' cellspacing='0' cellpadding='5'>")
        self.row(r, "Layer", layer.name())
        self.row(r, "Geometry Type", typ)
        self.row(r, "Feature Count", layer.featureCount())
        self.row(r, "CRS", layer.crs().authid() or layer.crs().description())
        self.row(r, "CRS Description", layer.crs().description())
        self.row(r, "Field Count", len(layer.fields()))
        r.append("</table>")

        if geometry:
            r += self.geometry_report(layer)
        if attributes:
            r += self.attribute_report(layer)
        if quality:
            r += self.quality_report(layer)
        if duplicates:
            r += self.duplicate_report(layer)

        return "".join(r)

    def geometry_name(self, layer):
        return {QgsWkbTypes.PointGeometry:"Point", QgsWkbTypes.LineGeometry:"Line",
                QgsWkbTypes.PolygonGeometry:"Polygon"}.get(layer.geometryType(), "Unknown")

    def geometry_report(self, layer):
        typ = self.geometry_name(layer)
        fs = list(layer.getFeatures())
        with_geom = [f for f in fs if f.hasGeometry()]
        r = ["<h2>2. Geometry Statistics</h2><table border='1' cellspacing='0' cellpadding='5'>"]
        self.row(r, "Features with geometry", len(with_geom))
        self.row(r, "Features without geometry", len(fs)-len(with_geom))
        da = QgsDistanceArea()
        da.setSourceCrs(layer.crs(), layer.transformContext())

        if typ == "Polygon":
            areas, perims = [], []
            for f in with_geom:
                try:
                    areas.append(abs(da.measureArea(f.geometry())))
                    perims.append(abs(da.measurePerimeter(f.geometry())))
                except Exception:
                    pass
            self.stats(r, "Area (m²)", areas)
            self.row(r, "Total Area (km²)", self.fmt(sum(areas)/1e6))
            self.row(r, "Total Area (hectares)", self.fmt(sum(areas)/1e4))
            self.row(r, "Total Area (acres)", self.fmt(sum(areas)/4046.8564224))
            self.stats(r, "Perimeter (m)", perims)
            self.row(r, "Total Perimeter (km)", self.fmt(sum(perims)/1000))
        elif typ == "Line":
            lengths = []
            for f in with_geom:
                try:
                    lengths.append(abs(da.measureLength(f.geometry())))
                except Exception:
                    pass
            self.stats(r, "Length (m)", lengths)
            self.row(r, "Total Length (km)", self.fmt(sum(lengths)/1000))
        elif typ == "Point":
            xs, ys = [], []
            for f in with_geom:
                try:
                    p = f.geometry().asPoint()
                    xs.append(p.x()); ys.append(p.y())
                except Exception:
                    pass
            if xs:
                self.row(r, "X minimum", self.fmt(min(xs)))
                self.row(r, "X maximum", self.fmt(max(xs)))
                self.row(r, "Y minimum", self.fmt(min(ys)))
                self.row(r, "Y maximum", self.fmt(max(ys)))
        r.append("</table>")
        return r

    def attribute_report(self, layer):
        fs = list(layer.getFeatures())
        r = ["<h2>3. Field-wise Attribute Statistics</h2>",
             "<table border='1' cellspacing='0' cellpadding='5'>",
             "<tr><th>Field</th><th>Type</th><th>Unique</th><th>Null / Empty</th><th>Duplicate Records</th><th>Min</th><th>Max</th><th>Average</th><th>Sum</th></tr>"]
        for fld in layer.fields():
            vals = [f[fld.name()] for f in fs]
            non = [v for v in vals if v is not None and str(v).strip() != ""]
            counts = Counter(self.norm(v) for v in non)
            dup = sum(c-1 for c in counts.values() if c > 1)
            mn = mx = av = sm = ""
            if self.is_numeric_field(fld):
                nums = []
                for v in non:
                    try: nums.append(float(v))
                    except (ValueError, TypeError): pass
                if nums:
                    mn, mx = self.fmt(min(nums)), self.fmt(max(nums))
                    av, sm = self.fmt(sum(nums)/len(nums)), self.fmt(sum(nums))
            r.append(f"<tr><td>{self.esc(fld.name())}</td><td>{self.esc(fld.typeName())}</td><td>{len(counts)}</td><td>{len(vals)-len(non)}</td><td>{dup}</td><td>{mn}</td><td>{mx}</td><td>{av}</td><td>{sm}</td></tr>")
        r.append("</table><h3>Category Distribution</h3>")
        for fld in layer.fields():
            if self.is_numeric_field(fld):
                continue
            vals = [str(f[fld.name()]).strip() for f in fs if f[fld.name()] is not None and str(f[fld.name()]).strip()]
            if not vals: continue
            counts = Counter(vals)
            r.append(f"<b>{self.esc(fld.name())}</b><table border='1' cellspacing='0' cellpadding='4'><tr><th>Value</th><th>Count</th></tr>")
            for v,c in counts.most_common(20):
                r.append(f"<tr><td>{self.esc(v)}</td><td>{c}</td></tr>")
            if len(counts)>20:
                r.append(f"<tr><td colspan='2'>Showing top 20 of {len(counts)} unique values.</td></tr>")
            r.append("</table><br>")
        return r

    def quality_report(self, layer):
        typ = self.geometry_name(layer)
        fs = list(layer.getFeatures())
        invalid = empty = multi = zero = 0
        for f in fs:
            if not f.hasGeometry() or f.geometry().isNull() or f.geometry().isEmpty():
                empty += 1; continue
            g = f.geometry()
            try:
                if not g.isGeosValid(): invalid += 1
            except Exception: pass
            try:
                if g.isMultipart(): multi += 1
            except Exception: pass
            if typ == "Polygon":
                try:
                    if g.area() == 0: zero += 1
                except Exception: pass
            elif typ == "Line":
                try:
                    if g.length() == 0: zero += 1
                except Exception: pass

        r = ["<h2>4. Data Quality Checks</h2><table border='1' cellspacing='0' cellpadding='5'>"]
        self.row(r, "Invalid geometries", invalid)
        self.row(r, "Empty / null geometries", empty)
        self.row(r, "Multipart geometries", multi)
        self.row(r, "Zero-area polygons" if typ=="Polygon" else "Zero-length lines" if typ=="Line" else "Coincident/zero check", zero)
        r.append("</table><h3>Suspicious Attribute Values</h3><table border='1' cellspacing='0' cellpadding='5'><tr><th>Field</th><th>Feature ID</th><th>Value</th><th>Issue</th></tr>")
        found = 0
        for fld in layer.fields():
            if not self.is_text_field(fld): continue
            for f in fs:
                v = f[fld.name()]
                if v is None: continue
                issue = self.text_issue(str(v))
                if issue:
                    found += 1
                    r.append(f"<tr><td>{self.esc(fld.name())}</td><td>{f.id()}</td><td>{self.esc(v)}</td><td>{self.esc(issue)}</td></tr>")
                    if found >= 200: break
            if found >= 200: break
        if found == 0:
            r.append("<tr><td colspan='4'>No suspicious text values detected.</td></tr>")
        r.append("</table>")
        return r

    def duplicate_report(self, layer):
        fs = list(layer.getFeatures())
        gc = Counter()
        for f in fs:
            if f.hasGeometry():
                try: gc[hashlib.sha1(bytes(f.geometry().asWkb())).hexdigest()] += 1
                except Exception: pass
        groups = sum(1 for c in gc.values() if c>1)
        records = sum(c-1 for c in gc.values() if c>1)
        r = ["<h2>5. Duplicate Analysis</h2><table border='1' cellspacing='0' cellpadding='5'>"]
        self.row(r, "Duplicate geometry groups", groups)
        self.row(r, "Features beyond first in duplicate geometry groups", records)
        r.append("</table><h3>Duplicate Values by Field</h3><table border='1' cellspacing='0' cellpadding='5'><tr><th>Field</th><th>Duplicate Value Groups</th><th>Duplicate Records</th></tr>")
        for fld in layer.fields():
            vals = [self.norm(f[fld.name()]) for f in fs if f[fld.name()] is not None and str(f[fld.name()]).strip()]
            c = Counter(vals)
            r.append(f"<tr><td>{self.esc(fld.name())}</td><td>{sum(1 for x in c.values() if x>1)}</td><td>{sum(x-1 for x in c.values() if x>1)}</td></tr>")
        r.append("</table>")
        return r

    def text_issue(self, text):
        if self.control_pattern.search(text): return "Non-printable/control character"
        if text != text.strip(): return "Leading or trailing whitespace"
        if self.multi_space_pattern.search(text): return "Multiple consecutive spaces"
        if self.edge_pattern.search(text): return "Leading or trailing punctuation/symbol"
        return ""

    def is_text_field(self, field):
        # QGIS 4.x / PyQt6-compatible text field detection.
        try:
            return field.type() in (
                QMetaType.Type.QString,
                QMetaType.Type.QChar,
            )
        except Exception:
            return "string" in field.typeName().lower() or "text" in field.typeName().lower()

    def is_numeric_field(self, field):
        # QGIS 4.x / PyQt6-compatible numeric field detection.
        try:
            return field.type() in (
                QMetaType.Type.Int,
                QMetaType.Type.UInt,
                QMetaType.Type.LongLong,
                QMetaType.Type.ULongLong,
                QMetaType.Type.Double,
                QMetaType.Type.Float,
            )
        except Exception:
            name = field.typeName().lower()
            return any(x in name for x in (
                "int", "double", "float", "real", "decimal", "numeric"
            ))

    def stats(self, r, label, vals):
        if not vals:
            for s in ("Minimum","Maximum","Average","Median"): self.row(r, f"{label} - {s}", "N/A")
            return
        a = sorted(vals); n = len(a)
        med = a[n//2] if n%2 else (a[n//2-1]+a[n//2])/2
        self.row(r, f"{label} - Minimum", self.fmt(min(a)))
        self.row(r, f"{label} - Maximum", self.fmt(max(a)))
        self.row(r, f"{label} - Average", self.fmt(sum(a)/n))
        self.row(r, f"{label} - Median", self.fmt(med))

    def row(self, r, k, v):
        r.append(f"<tr><td><b>{self.esc(k)}</b></td><td>{self.esc(v)}</td></tr>")

    def norm(self, v):
        return f"{v:.12g}" if isinstance(v, float) else str(v).strip()

    def fmt(self, v):
        if v is None: return ""
        return f"{v:,.6f}".rstrip("0").rstrip(".")

    def esc(self, v):
        return (str(v).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;").replace("'","&#39;"))
