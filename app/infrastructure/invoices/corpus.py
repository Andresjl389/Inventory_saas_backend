"""El corpus: las facturas reales y lo que una persona dijo que decían.

Es el activo que hace posible un modelo a la medida, y se está acumulando solo
desde la primera factura escaneada. Cada escaneo confirmado guarda tres cosas
que juntas valen más que cualquier modelo: la imagen original, la lectura cruda
del modelo y la versión corregida por quien tenía el papel en la mano.

Con eso se hacen las dos cosas que de otro modo serían adivinanza:

* **Medir.** `eval-invoices` corre el lector configurado sobre el corpus y
  dice, con números, si el modelo propio lee bien las facturas de *estos*
  proveedores -- que es lo único que importa, y que ningún benchmark público
  responde.
* **Afinar.** Los pares (imagen, JSON correcto) son exactamente el formato de
  entrenamiento de un modelo de visión. Mil facturas revisadas son mil
  ejemplos etiquetados que nadie tuvo que etiquetar a propósito.

La exportación recorre empresa por empresa porque las políticas RLS de
`invoice_scans` no tienen escape de plataforma: ni este proceso puede leer dos
tenants a la vez. Es más código, y es la propiedad que queremos.
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from sqlalchemy import select

from app.domain.invoices.entities.scan import LineAction, ScanStatus
from app.domain.invoices.scoring import ReadingScore, score_reading
from app.infrastructure.database.models.company import CompanyModel
from app.infrastructure.database.models.file import FileModel
from app.infrastructure.database.models.invoice import InvoiceScanModel
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.database.tenant_context import set_current_company, set_platform_admin
from app.infrastructure.storage.factory import get_file_storage

EXTENSION_BY_TYPE = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "application/pdf": ".pdf",
    "text/plain": ".txt",
    "text/csv": ".csv",
}
TYPE_BY_EXTENSION = {value: key for key, value in EXTENSION_BY_TYPE.items()}
TYPE_BY_EXTENSION[".jpeg"] = "image/jpeg"


@dataclass
class CorpusReport:
    companies: int = 0
    scans: int = 0
    written: int = 0
    # Escaneos cuya imagen ya no está en el almacenamiento.
    missing_files: int = 0
    # Escaneos sin lectura cruda guardada (de antes de que se guardara).
    unscored: int = 0
    header_hits: int = 0
    header_total: int = 0
    exact_lines: int = 0
    expected_lines: int = 0
    clean: int = 0

    def add(self, score: ReadingScore) -> None:
        self.header_hits += sum(1 for hit in score.header.values() if hit)
        self.header_total += len(score.header)
        self.exact_lines += score.lines.exact
        self.expected_lines += score.lines.expected
        if score.is_clean:
            self.clean += 1

    def as_dict(self) -> dict:
        scored = self.written - self.unscored
        return {
            "companies": self.companies,
            "scans": self.scans,
            "written": self.written,
            "missing_files": self.missing_files,
            "unscored": self.unscored,
            "header_accuracy": round(self.header_hits / self.header_total, 4)
            if self.header_total
            else None,
            "line_accuracy": round(self.exact_lines / self.expected_lines, 4)
            if self.expected_lines
            else None,
            "clean_readings": f"{self.clean}/{scored}" if scored else "0/0",
        }


def _truth(scan: InvoiceScanModel) -> dict:
    """Lo que la factura decía, según quien la tuvo en la mano.

    Incluye los renglones descartados: el flete estaba impreso en el papel, así
    que un modelo que lo lea está acertando. Lo que se hizo con cada renglón
    viaja aparte, en `action`.
    """
    return {
        "supplier_name": scan.supplier_name,
        "supplier_tax_id": scan.supplier_tax_id,
        "invoice_number": scan.invoice_number,
        "invoice_date": scan.invoice_date.isoformat() if scan.invoice_date else None,
        "total": str(scan.declared_total) if scan.declared_total is not None else None,
        "lines": [
            {
                "description": line.description,
                "code": line.code,
                "quantity": str(line.quantity),
                "unit_cost": str(line.unit_cost),
                "discount": str(line.discount),
                "tax": str(line.tax),
                "action": line.action.value
                if isinstance(line.action, LineAction)
                else str(line.action),
            }
            for line in scan.lines
        ],
    }


async def export_corpus(
    destination: Path,
    *,
    company_id: uuid.UUID | None = None,
    since: date | None = None,
    limit: int | None = None,
) -> CorpusReport:
    destination.mkdir(parents=True, exist_ok=True)
    storage = get_file_storage()
    report = CorpusReport()

    async with SessionFactory() as session:
        async with session.begin():
            await set_platform_admin(session, True)
            companies = (
                (
                    await session.execute(
                        select(CompanyModel.id).where(
                            CompanyModel.id == company_id if company_id else True  # noqa: E712
                        )
                    )
                )
                .scalars()
                .all()
            )

        for company in companies:
            report.companies += 1
            async with session.begin():
                await set_current_company(session, company)
                statement = (
                    select(InvoiceScanModel)
                    .where(
                        InvoiceScanModel.company_id == company,
                        InvoiceScanModel.status == ScanStatus.CONFIRMED,
                    )
                    .order_by(InvoiceScanModel.created_at)
                )
                if since is not None:
                    statement = statement.where(InvoiceScanModel.invoice_date >= since)
                scans = (await session.execute(statement)).scalars().all()

                for scan in scans:
                    if limit is not None and report.written >= limit:
                        return report
                    report.scans += 1
                    stored = (
                        await session.execute(select(FileModel).where(FileModel.id == scan.file_id))
                    ).scalar_one_or_none()
                    if stored is None:
                        report.missing_files += 1
                        continue
                    await _write(destination, scan, stored, storage, report)

    return report


async def _write(
    destination: Path,
    scan: InvoiceScanModel,
    stored: FileModel,
    storage,
    report: CorpusReport,
) -> None:
    extension = EXTENSION_BY_TYPE.get(stored.content_type, ".bin")
    document = f"{scan.id}{extension}"

    try:
        payload = b"".join([chunk async for chunk in storage.open(stored.storage_key)])
    except FileNotFoundError:
        report.missing_files += 1
        return

    (destination / document).write_bytes(payload)

    truth = _truth(scan)
    read = (scan.extraction or {}).get("read")
    record = {
        "scan_id": str(scan.id),
        "company_id": str(scan.company_id),
        "document": document,
        "content_type": stored.content_type,
        "source": (scan.extraction or {}).get("source"),
        "truth": truth,
        "read": read,
    }
    (destination / f"{scan.id}.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    report.written += 1
    if read is None:
        report.unscored += 1
    else:
        report.add(score_reading(read, truth))


@dataclass
class EvalReport:
    """Lo que el lector configurado logra sobre facturas de verdad."""

    documents: int = 0
    failures: list[str] = field(default_factory=list)
    clean: int = 0
    header_hits: int = 0
    header_total: int = 0
    exact_lines: int = 0
    expected_lines: int = 0
    missed_lines: int = 0
    extra_lines: int = 0
    seconds: list[float] = field(default_factory=list)

    def as_dict(self) -> dict:
        ordered = sorted(self.seconds)
        return {
            "documents": self.documents,
            "read_ok": self.documents - len(self.failures),
            "failures": self.failures[:10],
            "clean_readings": f"{self.clean}/{self.documents}",
            "header_accuracy": round(self.header_hits / self.header_total, 4)
            if self.header_total
            else None,
            "line_accuracy": round(self.exact_lines / self.expected_lines, 4)
            if self.expected_lines
            else None,
            # Los renglones que faltan son el error caro: mercancía que entra
            # al inventario sin estar en la factura, o al contrario.
            "missed_lines": self.missed_lines,
            "extra_lines": self.extra_lines,
            "seconds_median": round(ordered[len(ordered) // 2], 2) if ordered else None,
            "seconds_worst": round(ordered[-1], 2) if ordered else None,
        }


async def evaluate_corpus(directory: Path, *, extractor, limit: int | None = None) -> EvalReport:
    """Correr el lector sobre el corpus y comparar contra lo que ya se sabe.

    Es la única forma honesta de decidir si el modelo propio ya alcanza: no
    cómo le va en un benchmark, sino cuántas de *nuestras* facturas lee sin que
    nadie tenga que corregirlas.
    """
    import time

    report = EvalReport()

    for record_path in sorted(directory.glob("*.json")):
        if limit is not None and report.documents >= limit:
            break
        record = json.loads(record_path.read_text(encoding="utf-8"))
        document = directory / record["document"]
        if not document.exists():
            report.failures.append(f"{record_path.name}: falta {record['document']}")
            continue

        content_type = record.get("content_type") or TYPE_BY_EXTENSION.get(
            document.suffix.lower(), "application/octet-stream"
        )
        report.documents += 1

        started = time.perf_counter()
        try:
            invoice = await extractor.extract(document.read_bytes(), content_type, document.name)
        except Exception as exc:  # el lector falla: eso también es un resultado
            report.failures.append(f"{record_path.name}: {type(exc).__name__}: {exc}")
            continue
        finally:
            report.seconds.append(time.perf_counter() - started)

        score = score_reading(_as_read(invoice), record["truth"])
        report.header_hits += sum(1 for hit in score.header.values() if hit)
        report.header_total += len(score.header)
        report.exact_lines += score.lines.exact
        report.expected_lines += score.lines.expected
        report.missed_lines += score.lines.missed
        report.extra_lines += score.lines.extra
        if score.is_clean:
            report.clean += 1

    return report


def _as_read(invoice) -> dict:
    return {
        "supplier_name": invoice.supplier_name,
        "supplier_tax_id": invoice.supplier_tax_id,
        "invoice_number": invoice.invoice_number,
        "invoice_date": invoice.invoice_date.isoformat() if invoice.invoice_date else None,
        "total": str(invoice.total) if invoice.total is not None else None,
        "lines": [
            {
                "description": line.description,
                "code": line.code,
                "quantity": str(line.quantity),
                "unit_cost": str(line.unit_cost),
            }
            for line in invoice.lines
        ],
    }
