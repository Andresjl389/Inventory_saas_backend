"""El punto de composición del lector.

Un lector mal configurado tiene que doler al arrancar el escaneo. La
alternativa -- devolver una factura vacía -- haría que alguien confirmara
pensando que el papel no traía nada.
"""

import pytest

from app.domain.invoices.exceptions import InvoiceScanningDisabledError
from app.infrastructure.invoices.factory import get_invoice_extractor
from app.infrastructure.invoices.local_extractor import LocalModelInvoiceExtractor
from app.infrastructure.invoices.text_extractor import TextInvoiceExtractor
from app.shared.config.settings import settings


@pytest.fixture(autouse=True)
def _fresh_cache():
    get_invoice_extractor.cache_clear()
    yield
    get_invoice_extractor.cache_clear()


def test_scanning_is_off_until_the_server_has_a_gpu(monkeypatch):
    """El modelo quedó para después, así que el valor por defecto no finge que
    hay uno: dice que la capacidad está apagada."""
    monkeypatch.setattr(settings, "invoice_extractor", "disabled")

    with pytest.raises(InvoiceScanningDisabledError) as error:
        get_invoice_extractor()

    # 503: el cliente no hizo nada mal, este servidor no tiene la capacidad.
    assert error.value.status_code == 503
    assert error.value.code == "INVOICE_SCANNING_DISABLED"


def test_turning_it_on_is_two_environment_variables(monkeypatch):
    """La prueba de que diferir el modelo no dejó código a medias."""
    monkeypatch.setattr(settings, "invoice_extractor", "local")
    monkeypatch.setattr(settings, "invoice_local_url", "http://gpu-nueva:8000/v1")

    assert get_invoice_extractor().source == f"local:{settings.invoice_local_model}"


def test_the_text_reader_is_what_the_suite_gets():
    assert isinstance(get_invoice_extractor(), TextInvoiceExtractor)


def test_the_default_reader_is_our_own_model(monkeypatch):
    monkeypatch.setattr(settings, "invoice_extractor", "local")

    extractor = get_invoice_extractor()

    assert isinstance(extractor, LocalModelInvoiceExtractor)
    assert extractor.source == f"local:{settings.invoice_local_model}"


def test_our_own_model_needs_no_api_key(monkeypatch):
    """La razón de ser del modelo propio: ninguna llave de nadie."""
    monkeypatch.setattr(settings, "invoice_extractor", "local")
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    monkeypatch.setattr(settings, "invoice_local_api_key", None)

    assert get_invoice_extractor() is not None


def test_claude_without_a_key_fails_loudly_instead_of_reading_nothing(monkeypatch):
    monkeypatch.setattr(settings, "invoice_extractor", "claude")
    monkeypatch.setattr(settings, "anthropic_api_key", None)

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        get_invoice_extractor()


def test_claude_is_optional_and_says_how_to_install_it(monkeypatch):
    """Es la vara de medir, no el camino: su SDK vive en un extra."""
    monkeypatch.setattr(settings, "invoice_extractor", "claude")
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-not-a-real-key")

    try:
        import anthropic  # noqa: F401
    except ImportError:
        with pytest.raises(RuntimeError, match="extra claude|--extra claude"):
            get_invoice_extractor()
        return

    assert get_invoice_extractor().source == f"claude:{settings.invoice_model}"
