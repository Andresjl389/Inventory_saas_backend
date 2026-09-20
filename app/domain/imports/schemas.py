"""What each importable entity expects, declaratively.

One table drives three things that must never disagree: the downloadable
template, the mapping screen's list of target fields ("etiquetas"), and the
validation that runs on every row. Adding a column to an import means adding a
FieldSpec here and nothing else.
"""

from dataclasses import dataclass, field
from enum import StrEnum

from app.domain.imports.coercion import FieldType


class ImportEntity(StrEnum):
    CATEGORIES = "CATEGORIES"
    PRODUCTS = "PRODUCTS"
    WAREHOUSES = "WAREHOUSES"
    CUSTOMERS = "CUSTOMERS"
    SUPPLIERS = "SUPPLIERS"
    STOCK = "STOCK"


DOCUMENT_TYPES = ("NIT", "CC", "CE", "PASSPORT", "RUT", "OTHER")


@dataclass(frozen=True, slots=True)
class FieldSpec:
    key: str
    label: str
    type: FieldType
    required: bool = False
    # Header texts seen in the wild that mean this field. Matched after
    # stripping accents, case and punctuation, so "Precio de Venta" and
    # "precio_venta" both land here.
    aliases: tuple[str, ...] = ()
    help: str = ""
    enum_values: tuple[str, ...] = ()
    example: str = ""


@dataclass(frozen=True, slots=True)
class EntitySchema:
    entity: ImportEntity
    label: str
    # The field whose value decides create-vs-update. Two rows with the same
    # key in one file are folded together, last one winning.
    key_field: str
    fields: tuple[FieldSpec, ...]
    description: str = ""
    options: tuple[str, ...] = field(default_factory=tuple)

    def by_key(self, key: str) -> FieldSpec | None:
        return next((spec for spec in self.fields if spec.key == key), None)

    @property
    def required_keys(self) -> tuple[str, ...]:
        return tuple(spec.key for spec in self.fields if spec.required)


CATEGORIES_SCHEMA = EntitySchema(
    entity=ImportEntity.CATEGORIES,
    label="Categorías",
    key_field="name",
    description="Categorías de productos. Se identifican por nombre.",
    fields=(
        FieldSpec(
            "name",
            "Nombre",
            FieldType.TEXT,
            required=True,
            aliases=("categoria", "category", "nombre categoria", "categoria nombre"),
            example="Herramientas",
        ),
        FieldSpec(
            "description",
            "Descripción",
            FieldType.TEXT,
            aliases=("descripcion", "description", "detalle", "observaciones"),
            example="Herramientas manuales",
        ),
    ),
)

PRODUCTS_SCHEMA = EntitySchema(
    entity=ImportEntity.PRODUCTS,
    label="Productos",
    key_field="sku",
    description="Catálogo de productos. Se identifican por SKU dentro de la empresa.",
    options=("create_missing_categories",),
    fields=(
        FieldSpec(
            "sku",
            "SKU",
            FieldType.TEXT,
            required=True,
            aliases=("codigo", "código", "code", "referencia", "ref", "item", "cod"),
            help="Código único del producto dentro de la empresa.",
            example="MAR-01",
        ),
        FieldSpec(
            "name",
            "Nombre",
            FieldType.TEXT,
            required=True,
            aliases=("producto", "descripcion producto", "nombre producto", "product", "articulo"),
            example="Martillo de carpintero",
        ),
        FieldSpec(
            "description",
            "Descripción",
            FieldType.TEXT,
            aliases=("descripcion", "detalle", "observaciones", "notas"),
        ),
        FieldSpec(
            "barcode",
            "Código de barras",
            FieldType.TEXT,
            aliases=("codigo de barras", "barras", "ean", "upc", "barcode"),
        ),
        FieldSpec(
            "category",
            "Categoría",
            FieldType.TEXT,
            aliases=("categoria", "familia", "linea", "grupo", "category"),
            help="Por nombre. Puede crearse sola si activas esa opción.",
            example="Herramientas",
        ),
        FieldSpec(
            "cost_price",
            "Precio de costo",
            FieldType.DECIMAL,
            aliases=("costo", "precio costo", "precio de compra", "cost", "valor costo"),
            example="8000",
        ),
        FieldSpec(
            "sale_price",
            "Precio de venta",
            FieldType.DECIMAL,
            aliases=("precio", "precio venta", "pvp", "valor", "price", "precio publico"),
            example="15000",
        ),
        FieldSpec(
            "min_stock",
            "Stock mínimo",
            FieldType.DECIMAL,
            aliases=("minimo", "stock minimo", "punto de reorden", "reorden", "min"),
            help="Umbral para la alerta de stock bajo. 0 la desactiva.",
            example="10",
        ),
        FieldSpec(
            "is_active",
            "Activo",
            FieldType.BOOLEAN,
            aliases=("activo", "estado", "habilitado", "active", "vigente"),
            example="SI",
        ),
    ),
)

WAREHOUSES_SCHEMA = EntitySchema(
    entity=ImportEntity.WAREHOUSES,
    label="Bodegas",
    key_field="name",
    description="Bodegas o puntos de venta. Se identifican por nombre.",
    fields=(
        FieldSpec(
            "name",
            "Nombre",
            FieldType.TEXT,
            required=True,
            aliases=("bodega", "almacen", "almacén", "deposito", "sucursal", "warehouse"),
            example="Bodega Central",
        ),
        FieldSpec(
            "address",
            "Dirección",
            FieldType.TEXT,
            aliases=("direccion", "ubicacion", "address", "sede"),
        ),
        FieldSpec("is_active", "Activa", FieldType.BOOLEAN, aliases=("activo", "estado")),
    ),
)

_PARTY_FIELDS = (
    FieldSpec(
        "name",
        "Nombre",
        FieldType.TEXT,
        required=True,
        aliases=("nombre", "razon social", "razón social", "cliente", "proveedor", "name"),
        example="Distribuciones del Norte",
    ),
    FieldSpec(
        "document_type",
        "Tipo de documento",
        FieldType.ENUM,
        enum_values=DOCUMENT_TYPES,
        aliases=("tipo documento", "tipo doc", "tipo identificacion", "tipo id"),
        example="NIT",
    ),
    FieldSpec(
        "document_number",
        "Número de documento",
        FieldType.TEXT,
        aliases=("documento", "nit", "cedula", "cédula", "identificacion", "rut", "doc", "cc"),
        help="Junto con el tipo, identifica al registro para no duplicarlo.",
        example="900123456",
    ),
    FieldSpec(
        "email",
        "Correo",
        FieldType.TEXT,
        aliases=("correo", "e-mail", "mail", "correo electronico"),
    ),
    FieldSpec(
        "phone",
        "Teléfono",
        FieldType.TEXT,
        aliases=("telefono", "celular", "movil", "tel", "contacto"),
    ),
    FieldSpec(
        "address",
        "Dirección",
        FieldType.TEXT,
        aliases=("direccion", "domicilio", "ubicacion"),
    ),
    FieldSpec("is_active", "Activo", FieldType.BOOLEAN, aliases=("activo", "estado")),
)

CUSTOMERS_SCHEMA = EntitySchema(
    entity=ImportEntity.CUSTOMERS,
    label="Clientes",
    key_field="document_number",
    description=("Clientes. Se identifican por número de documento; sin documento, por nombre."),
    fields=_PARTY_FIELDS,
)

SUPPLIERS_SCHEMA = EntitySchema(
    entity=ImportEntity.SUPPLIERS,
    label="Proveedores",
    key_field="document_number",
    description=("Proveedores. Se identifican por número de documento; sin documento, por nombre."),
    fields=_PARTY_FIELDS,
)

STOCK_SCHEMA = EntitySchema(
    entity=ImportEntity.STOCK,
    label="Stock inicial",
    key_field="sku",
    description=(
        "Saldos iniciales por bodega. Cada fila genera un movimiento de ajuste, "
        "así que el inventario queda con su historial desde el primer día."
    ),
    options=("replace_existing",),
    fields=(
        FieldSpec(
            "sku",
            "SKU",
            FieldType.TEXT,
            required=True,
            aliases=("codigo", "referencia", "ref", "producto", "item"),
            help="El producto debe existir ya.",
            example="MAR-01",
        ),
        FieldSpec(
            "warehouse",
            "Bodega",
            FieldType.TEXT,
            required=True,
            aliases=("bodega", "almacen", "deposito", "sucursal", "warehouse"),
            help="Por nombre. La bodega debe existir ya.",
            example="Bodega Central",
        ),
        FieldSpec(
            "quantity",
            "Cantidad",
            FieldType.DECIMAL,
            required=True,
            aliases=("cantidad", "existencia", "saldo", "stock", "qty", "unidades"),
            example="25",
        ),
    ),
)

SCHEMAS: dict[ImportEntity, EntitySchema] = {
    ImportEntity.CATEGORIES: CATEGORIES_SCHEMA,
    ImportEntity.PRODUCTS: PRODUCTS_SCHEMA,
    ImportEntity.WAREHOUSES: WAREHOUSES_SCHEMA,
    ImportEntity.CUSTOMERS: CUSTOMERS_SCHEMA,
    ImportEntity.SUPPLIERS: SUPPLIERS_SCHEMA,
    ImportEntity.STOCK: STOCK_SCHEMA,
}

# The order a company should import in: a product needs its category, stock
# needs the product and the warehouse.
RECOMMENDED_ORDER: tuple[ImportEntity, ...] = (
    ImportEntity.CATEGORIES,
    ImportEntity.WAREHOUSES,
    ImportEntity.PRODUCTS,
    ImportEntity.CUSTOMERS,
    ImportEntity.SUPPLIERS,
    ImportEntity.STOCK,
)


def schema_for(entity: ImportEntity) -> EntitySchema:
    return SCHEMAS[entity]
