def classFactory(iface):
    from .gis_data_inspector import GISDataInspector
    return GISDataInspector(iface)
