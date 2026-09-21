"""Attachments stored on the local filesystem."""

import hashlib

from tests.api.helpers import PNG_BYTES, create_product, headers, login, register, tenant, upload
from tests.conftest import requires_db

pytestmark = requires_db


async def test_upload_and_download_a_product_image(client, engine, unique_email):
    hdrs, _ = await tenant(client, engine, unique_email)
    product_id = await create_product(client, hdrs)

    uploaded = await upload(
        client, hdrs, owner_type="PRODUCT", owner_id=product_id, filename="martillo.png"
    )

    assert uploaded.status_code == 201, uploaded.text
    body = uploaded.json()
    assert body["owner_type"] == "PRODUCT"
    assert body["owner_id"] == product_id
    assert body["content_type"] == "image/png"
    assert body["size_bytes"] == len(PNG_BYTES)
    assert body["checksum"] == hashlib.sha256(PNG_BYTES).hexdigest()
    assert body["download_url"] == f"/api/v1/files/{body['id']}/content"

    downloaded = await client.get(body["download_url"], headers=hdrs)
    assert downloaded.status_code == 200
    assert downloaded.content == PNG_BYTES
    assert downloaded.headers["content-type"].startswith("image/png")
    assert downloaded.headers["x-content-type-options"] == "nosniff"
    assert 'inline; filename="martillo.png"' in downloaded.headers["content-disposition"]


async def test_listing_a_products_images(client, engine, unique_email):
    hdrs, _ = await tenant(client, engine, unique_email)
    first = await create_product(client, hdrs, "P1")
    second = await create_product(client, hdrs, "P2")
    await upload(client, hdrs, owner_type="PRODUCT", owner_id=first)
    await upload(client, hdrs, owner_type="PRODUCT", owner_id=first)
    await upload(client, hdrs, owner_type="PRODUCT", owner_id=second)

    listed = await client.get(
        "/api/v1/files",
        headers=hdrs,
        params={"owner_type": "PRODUCT", "owner_id": first},
    )

    assert listed.json()["total"] == 2


async def test_the_stored_path_is_generated_not_taken_from_the_filename(
    client, engine, storage_root, unique_email
):
    """A filename cannot steer where the bytes land."""
    hdrs, company_id = await tenant(client, engine, unique_email)

    uploaded = await upload(
        client, hdrs, filename="../../../../etc/passwd.png", content_type="image/png"
    )

    assert uploaded.status_code == 201
    # Echoed back with no separators and no leading dots...
    stored_name = uploaded.json()["filename"]
    assert "/" not in stored_name and "\\" not in stored_name
    assert not stored_name.startswith(".")
    # ...and everything written stays under this company's own prefix.
    written = [p for p in storage_root.rglob("*") if p.is_file()]
    assert len(written) == 1
    assert written[0].relative_to(storage_root).parts[0] == company_id
    assert written[0].suffix == ".png"


async def test_a_disallowed_content_type_is_refused(client, engine, storage_root, unique_email):
    hdrs, _ = await tenant(client, engine, unique_email)

    response = await upload(
        client, hdrs, content=b"<?php ?>", filename="shell.php", content_type="application/x-php"
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"
    assert [p for p in storage_root.rglob("*") if p.is_file()] == []


async def test_an_oversized_upload_is_refused_and_leaves_nothing_behind(
    client, engine, storage_root, unique_email
):
    """The cap is 1 MB in the test settings and is enforced mid-stream."""
    hdrs, _ = await tenant(client, engine, unique_email)

    response = await upload(
        client,
        hdrs,
        content=b"x" * (2 * 1024 * 1024),
        filename="big.pdf",
        content_type="application/pdf",
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"
    assert [p for p in storage_root.rglob("*") if p.is_file()] == [], (
        "a rejected upload must not leave a partial blob"
    )


async def test_an_empty_file_is_refused(client, engine, unique_email):
    hdrs, _ = await tenant(client, engine, unique_email)

    response = await upload(client, hdrs, content=b"", filename="empty.png")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "EMPTY_FILE"


async def test_a_file_cannot_be_attached_to_another_tenants_product(client, engine):
    hdrs_a, _ = await tenant(client, engine, "a@example.com", "Acme")
    hdrs_b, _ = await tenant(client, engine, "b@example.com", "Globex")
    product_a = await create_product(client, hdrs_a)

    response = await upload(client, hdrs_b, owner_type="PRODUCT", owner_id=product_a)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PRODUCT_NOT_FOUND"


async def test_attaching_to_a_product_requires_an_owner_id(client, engine, unique_email):
    hdrs, _ = await tenant(client, engine, unique_email)

    response = await upload(client, hdrs, owner_type="PRODUCT")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "OWNER_ID_REQUIRED"


async def test_files_are_invisible_across_tenants(client, engine):
    hdrs_a, _ = await tenant(client, engine, "a@example.com", "Acme")
    hdrs_b, _ = await tenant(client, engine, "b@example.com", "Globex")
    file_id = (await upload(client, hdrs_a)).json()["id"]

    assert (await client.get(f"/api/v1/files/{file_id}", headers=hdrs_b)).status_code == 404
    assert (await client.get(f"/api/v1/files/{file_id}/content", headers=hdrs_b)).status_code == 404
    assert (await client.get("/api/v1/files", headers=hdrs_b)).json()["total"] == 0


async def test_deleting_a_file_removes_the_row_and_the_blob(
    client, engine, storage_root, unique_email
):
    hdrs, _ = await tenant(client, engine, unique_email)
    file_id = (await upload(client, hdrs)).json()["id"]
    assert len([p for p in storage_root.rglob("*") if p.is_file()]) == 1

    deleted = await client.delete(f"/api/v1/files/{file_id}", headers=hdrs)

    assert deleted.status_code == 204
    assert (await client.get(f"/api/v1/files/{file_id}", headers=hdrs)).status_code == 404
    assert [p for p in storage_root.rglob("*") if p.is_file()] == []


async def test_a_seller_can_read_attachments_but_not_upload_them(client, engine, unique_email):
    owner, company_id = await tenant(client, engine, unique_email)
    await register(client, "seller@example.com")
    await client.post(
        "/api/v1/companies/current/members",
        headers=owner,
        json={"email": "seller@example.com", "role": "SELLER"},
    )
    seller = headers(await login(client, "seller@example.com"), company_id)

    assert (await client.get("/api/v1/files", headers=seller)).status_code == 200

    refused = await upload(client, seller)
    assert refused.status_code == 403
    assert refused.json()["error"]["details"]["required_permission"] == "files.write"


async def test_the_orphan_sweep_reclaims_blobs_with_no_row(
    client, engine, run_job, storage_root, unique_email
):
    """Uploads write the blob first, so a failed request leaves bytes behind."""
    import os
    import time

    from app.infrastructure.jobs.file_maintenance import GRACE_SECONDS, sweep_orphan_files

    hdrs, company_id = await tenant(client, engine, unique_email)
    kept = (await upload(client, hdrs)).json()

    orphan = storage_root / company_id / "company" / "2020" / "01" / "orphan.png"
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_bytes(PNG_BYTES)
    # Age it past the grace period; a blob written seconds ago is left alone
    # because its row may still be in an uncommitted transaction.
    old = time.time() - GRACE_SECONDS - 60
    os.utime(orphan, (old, old))

    result = await sweep_orphan_files()

    assert result["removed"] == 1
    assert not orphan.exists()
    assert (await client.get(kept["download_url"], headers=hdrs)).status_code == 200


async def test_a_fresh_orphan_is_left_alone(client, engine, run_job, storage_root, unique_email):
    from app.infrastructure.jobs.file_maintenance import sweep_orphan_files

    hdrs, company_id = await tenant(client, engine, unique_email)
    fresh = storage_root / company_id / "company" / "2026" / "01" / "fresh.png"
    fresh.parent.mkdir(parents=True, exist_ok=True)
    fresh.write_bytes(PNG_BYTES)

    result = await sweep_orphan_files()

    assert result["removed"] == 0
    assert fresh.exists()
