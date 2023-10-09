from component.message import cm

__all__ = ["MATRIX_NAMES", "TABLE_NAMES", "NO_VALUE", "SCHEMA"]

MATRIX_NAMES = ["src", "dst"]
TABLE_NAMES = ["code", "desc", "color"]

# Set a value for missing reclassifications
NO_VALUE = 999

SCHEMA = {
    "id": [cm.rec.table.schema.id, "number"],
    "code": [cm.rec.table.schema.code, "number"],
    "desc": [cm.rec.table.schema.description, "string"],
    "color": [cm.rec.table.schema.color, "hexa"],
}
