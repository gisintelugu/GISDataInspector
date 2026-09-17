# GIS Data Inspector

Professional QGIS vector data statistics and QA/QC inspection plugin.

## V1.6.0 — Trial & Licensing
- 24-hour first-use trial
- Machine-bound trial state
- Basic system-clock rollback detection
- RSA/SHA-256 signed commercial licenses
- Machine-bound license activation
- **Trial / License** menu for status and activation
- Polygon, line and point inspection
- Geometry, attribute, quality and duplicate analysis
- Export report to HTML, PDF and Excel (.xlsx)

## Licensing architecture
The plugin contains only the public verification key. The private signing key must remain with the publisher and must never be committed to this repository.

For a commercial license, collect the customer's Machine ID from the expired-trial dialog and generate a signed key using the private license generator.

> Note: Python plugins are client-side source code, so no offline Python licensing mechanism is completely tamper-proof. The signed-license design prevents ordinary key forgery; a future online activation service can provide stronger enforcement and centralized activation/revocation.

## Previous versions
### V1.5.3
- Fixed Qt 6 PDF page-margin handling for QGIS 4

### V1.5.2
- Fixed Qt 6 PDF page-margin enum for QGIS 4

### V1.5.1
- Fixed PDF export for QGIS 4 / Qt 6
