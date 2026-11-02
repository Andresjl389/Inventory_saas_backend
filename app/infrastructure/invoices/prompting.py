"""Lo que se le pide a un modelo para leer una factura, y cómo se recibe.

Vive aparte de los adaptadores porque es lo único que tienen que compartir: si
el modelo propio y el de referencia no reciben exactamente las mismas
instrucciones ni devuelven exactamente la misma forma, compararlos no mide el
modelo, mide el prompt.

Dos decisiones que importan más que la elección del modelo:

* **El modelo transcribe, no interpreta.** Devuelve las cifras como cadenas,
  tal como están impresas ("15.000", "2,5"), y quien las vuelve números es el
  mismo `to_decimal` que usa el importador de Excel. Pedirle números al modelo
  sería pedirle que adivine si 15.000 son quince mil o quince -- decisión que
  ya está resuelta y probada en `coercion.py`, y que un modelo pequeño
  resuelve mal con frecuencia.
* **Lo ilegible se avisa, no se completa.** Un renglón que no se pudo leer
  llega con advertencias y baja confianza, y la revisión lo resalta. Rellenarlo
  con algo plausible es la única forma de que una factura mal leída entre al
  inventario sin que nadie lo note.
"""

from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, Field

from app.domain.imports.coercion import CoercionError, to_date, to_decimal, to_text
from app.domain.invoices.extraction import ExtractedInvoice, ExtractedLine
from app.domain.shared.money import ZERO

SYSTEM = """\
Eres un lector de facturas de compra de tiendas de barrio en Colombia.

Tu trabajo es transcribir lo que está impreso en el documento, no interpretarlo.

Reglas:
- Copia las cifras EXACTAMENTE como aparecen, como texto: "15.000", "2,5", "$ 1.200".
  No las conviertas, no les quites ni les pongas separadores, no las redondees.
- Copia la descripción de cada renglón como está impresa, abreviaturas incluidas.
- Si un dato no se alcanza a leer, pon null y explica por qué en "warnings".
  Nunca completes, corrijas ni adivines un dato que no se ve.
- No agregues renglones que no estén en el papel ni unas dos renglones en uno.
- Los cargos que no son mercancía (flete, transporte, bolsas, envase, descuentos
  globales) también van como renglones: quien revisa los descarta.
- "confidence" de cada renglón: 1.0 si está impreso y nítido, menos si está
  borroso, tachado, cortado o escrito a mano.
- Si el documento no es una factura ni un remito, devuelve "lines" vacío y dilo
  en "warnings".
"""

PROMPT = (
    "Transcribe esta factura de compra. Devuelve el encabezado (proveedor, NIT, "
    "número, fecha, moneda, subtotal, impuesto y total) y todos los renglones."
)

# Un modelo propio hay que acotarlo: sin tope, un renglón mal leído puede
# ponerlo a repetir hasta llenar el contexto.
MAX_OUTPUT_TOKENS = 8192


def _as_text(value: Any) -> Any:
    """Aceptar un número donde se pidió texto.

    El prompt pide las cifras como cadenas y un modelo grande obedece; uno de
    7B devuelve `"quantity": 2` cada tantas facturas. Rechazar la factura
    entera por eso sería perder la lectura por una comilla.
    """
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int | float | Decimal):
        return str(value)
    return value


def _as_confidence(value: Any) -> Any:
    """Una confianza fuera de rango se acomoda, no tumba la factura.

    Un modelo propio devuelve 95 en vez de 0.95 con cierta frecuencia; la
    intención es clara y es recuperable.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 1.0
    if number > 1:
        number = number / 100 if number <= 100 else 1.0
    return min(max(number, 0.0), 1.0)


def _as_list(value: Any) -> Any:
    return [] if value is None else value


Text = Annotated[str | None, BeforeValidator(_as_text)]
Confidence = Annotated[float, BeforeValidator(_as_confidence)]
Warnings = Annotated[list[str], BeforeValidator(_as_list)]


class LinePayload(BaseModel):
    """El renglón como lo devuelve el modelo: todo texto, nada convertido."""

    description: Annotated[str, BeforeValidator(_as_text)]
    quantity: Text = None
    unit_cost: Text = None
    code: Text = None
    unit: Text = None
    discount: Text = None
    tax: Text = None
    total: Text = None
    confidence: Confidence = Field(default=1.0, ge=0, le=1)
    warnings: Warnings = Field(default_factory=list)


class InvoicePayload(BaseModel):
    """Lo que no venga es lo que no se leyó.

    Con gramática forzada el modelo trae todas las claves; sin ella, uno chico
    omite las que quedarían en null. Exigirlas al validar perdería la factura
    entera por un `"unit"` que ni siquiera estaba impreso.
    """

    supplier_name: Text = None
    supplier_tax_id: Text = None
    invoice_number: Text = None
    invoice_date: Text = None
    currency: Text = None
    subtotal: Text = None
    tax: Text = None
    total: Text = None
    lines: list[LinePayload] = Field(default_factory=list)
    warnings: Warnings = Field(default_factory=list)


def json_schema() -> dict:
    """El esquema para la decodificación guiada de un servidor propio.

    vLLM, llama.cpp y Ollama saben forzar la salida a un esquema JSON. Con eso,
    un modelo de 7B deja de inventarse campos, que es la mitad de la diferencia
    entre un modelo grande y uno pequeño en esta tarea.
    """
    return _closed(InvoicePayload.model_json_schema())


def _closed(schema: dict) -> dict:
    """Cerrar cada objeto del esquema a sus campos declarados, y exigirlos todos.

    Pydantic no agrega `additionalProperties: false`, y sin eso la gramática
    deja que el modelo invente campos. Un modelo grande no lo hace; uno de 7B
    sí, y el campo inventado se lleva por delante el que faltaba.

    Los campos tienen valor por defecto para que validar sea tolerante, pero la
    gramática los pide todos: un dato ilegible tiene que llegar como null
    explícito, no como una clave que el modelo decidió saltarse.
    """
    if schema.get("type") == "object":
        schema["additionalProperties"] = False
        if "properties" in schema:
            schema["required"] = list(schema["properties"])
    for value in schema.values():
        if isinstance(value, dict):
            _closed(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    _closed(item)
    return schema


def _amount(raw: str | None, warnings: list[str], label: str) -> Decimal | None:
    """Convertir una cifra impresa, o avisar. Nunca inventa un número."""
    if raw is None or not str(raw).strip():
        return None
    try:
        return to_decimal(raw)
    except CoercionError:
        warnings.append(f"{label}: no se pudo leer {raw!r} como número")
        return None


def _as_date(raw: str | None, warnings: list[str]) -> date | None:
    if raw is None or not str(raw).strip():
        return None
    try:
        return to_date(raw)
    except CoercionError:
        warnings.append(f"fecha: no se pudo leer {raw!r}")
        return None


def _as_line(payload: LinePayload) -> ExtractedLine | None:
    """Un renglón del modelo como renglón del dominio.

    Una cantidad ilegible se asume 1 con aviso -- el papel igual trae el
    renglón y descartarlo escondería mercancía -- pero un costo ilegible deja
    el renglón en cero con aviso, porque inventar un precio sí falsea la compra.
    """
    description = to_text(payload.description)
    if not description:
        return None

    warnings = list(payload.warnings)
    quantity = _amount(payload.quantity, warnings, "cantidad")
    if quantity is None or quantity <= 0:
        warnings.append("cantidad ilegible: se asumió 1, confírmala")
        quantity = Decimal("1")

    unit_cost = _amount(payload.unit_cost, warnings, "costo unitario")
    if unit_cost is None or unit_cost < 0:
        warnings.append("costo unitario ilegible: quedó en 0, escríbelo a mano")
        unit_cost = ZERO

    return ExtractedLine(
        description=description,
        quantity=quantity,
        unit_cost=unit_cost,
        code=to_text(payload.code),
        unit=to_text(payload.unit),
        discount=_amount(payload.discount, warnings, "descuento") or ZERO,
        tax=_amount(payload.tax, warnings, "impuesto") or ZERO,
        total=_amount(payload.total, warnings, "total del renglón"),
        confidence=payload.confidence,
        warnings=tuple(warnings),
    )


def to_extracted(payload: InvoicePayload, *, source: str) -> ExtractedInvoice:
    """La respuesta del modelo, ya validada, como factura del dominio."""
    warnings = list(payload.warnings)
    lines = tuple(line for line in map(_as_line, payload.lines) if line is not None)

    return ExtractedInvoice(
        lines=lines,
        supplier_name=to_text(payload.supplier_name),
        supplier_tax_id=to_text(payload.supplier_tax_id),
        invoice_number=to_text(payload.invoice_number),
        invoice_date=_as_date(payload.invoice_date, warnings),
        currency=to_text(payload.currency),
        subtotal=_amount(payload.subtotal, warnings, "subtotal"),
        tax=_amount(payload.tax, warnings, "impuesto"),
        total=_amount(payload.total, warnings, "total"),
        source=source,
        warnings=tuple(warnings),
    )
