"""Dataset upload, listing, preview, column mapping, and deletion tests."""

import io
import uuid

from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings

VALID_CSV = (
    b"id,name,price,in_stock,added_on\n"
    b"1,Widget,9.99,true,2024-01-05\n"
    b"2,Gadget,19.99,false,2024-01-06\n"
    b"3,Gizmo,5.00,true,2024-01-07\n"
)
MALFORMED_CSV = b"id,name,price\n1,Widget,9.99\n2,Gadget\n"
DUPLICATE_COLUMN_CSV = b"id,id,price\n1,2,9.99\n"
EMPTY_CSV = b""


def _valid_xlsx_bytes() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["id", "name", "price"])
    sheet.append([1, "Widget", 9.99])
    sheet.append([2, "Gadget", 19.99])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _register(client: TestClient, email: str) -> dict:
    response = client.post(
        "/auth/register",
        json={"email": email, "password": "correct horse battery", "full_name": "Test User"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _upload_csv(
    client: TestClient, token: str, content: bytes = VALID_CSV, filename: str = "products.csv"
):
    return client.post(
        "/datasets/upload",
        headers=_auth_headers(token),
        files={"file": (filename, content, "text/csv")},
    )


def test_successful_csv_upload(client: TestClient) -> None:
    user = _register(client, "csv-upload@example.com")

    response = _upload_csv(client, user["access_token"])

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "ready"
    assert body["row_count"] == 3
    assert body["column_count"] == 5
    assert body["file_type"] == "csv"
    assert "id" in body  # dataset identifier present in the response


def test_successful_excel_upload(client: TestClient) -> None:
    user = _register(client, "xlsx-upload@example.com")

    response = client.post(
        "/datasets/upload",
        headers=_auth_headers(user["access_token"]),
        files={
            "file": (
                "products.xlsx",
                _valid_xlsx_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "ready"
    assert body["row_count"] == 2
    assert body["column_count"] == 3
    assert body["file_type"] == "xlsx"


def test_unsupported_file_type_rejected(client: TestClient) -> None:
    user = _register(client, "bad-type@example.com")

    response = client.post(
        "/datasets/upload",
        headers=_auth_headers(user["access_token"]),
        files={"file": ("notes.txt", b"hello world", "text/plain")},
    )

    assert response.status_code == 415
    assert response.json()["detail"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_oversized_file_rejected(client: TestClient) -> None:
    user = _register(client, "oversized@example.com")
    settings = get_settings()
    original_limit = settings.max_upload_size_bytes
    settings.max_upload_size_bytes = 10  # 10 bytes - VALID_CSV is larger

    try:
        response = _upload_csv(client, user["access_token"])
    finally:
        settings.max_upload_size_bytes = original_limit

    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "FILE_TOO_LARGE"


def test_empty_file_rejected(client: TestClient) -> None:
    user = _register(client, "empty@example.com")

    response = _upload_csv(client, user["access_token"], content=EMPTY_CSV, filename="empty.csv")

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "EMPTY_FILE"


def test_malformed_csv_rejected(client: TestClient) -> None:
    user = _register(client, "malformed@example.com")

    response = _upload_csv(
        client, user["access_token"], content=MALFORMED_CSV, filename="malformed.csv"
    )

    assert response.status_code == 400
    body = response.json()["detail"]
    assert body["code"] == "MALFORMED_CSV"
    assert len(body["findings"]) >= 1


def test_duplicate_column_names_rejected(client: TestClient) -> None:
    user = _register(client, "dupcols@example.com")

    response = _upload_csv(
        client, user["access_token"], content=DUPLICATE_COLUMN_CSV, filename="dupcols.csv"
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "DUPLICATE_COLUMN_NAMES"


def test_dataset_metadata_persisted(client: TestClient) -> None:
    user = _register(client, "metadata@example.com")
    upload = _upload_csv(client, user["access_token"]).json()

    response = client.get(f"/datasets/{upload['id']}", headers=_auth_headers(user["access_token"]))

    assert response.status_code == 200
    body = response.json()
    assert body["file_size_bytes"] == len(VALID_CSV)
    assert body["row_count"] == 3
    assert body["column_count"] == 5
    assert body["status"] == "ready"


def test_preview_generation(client: TestClient) -> None:
    user = _register(client, "preview@example.com")
    upload = _upload_csv(client, user["access_token"]).json()

    response = client.get(
        f"/datasets/{upload['id']}/preview", headers=_auth_headers(user["access_token"])
    )

    assert response.status_code == 200
    body = response.json()
    assert body["columns"] == ["id", "name", "price", "in_stock", "added_on"]
    assert body["returned_row_count"] == 3
    assert body["rows"][0]["name"] == "Widget"


def test_column_type_inference(client: TestClient) -> None:
    user = _register(client, "inference@example.com")
    upload = _upload_csv(client, user["access_token"]).json()

    response = client.get(
        f"/datasets/{upload['id']}/columns", headers=_auth_headers(user["access_token"])
    )

    assert response.status_code == 200
    columns = {c["normalized_name"]: c for c in response.json()["columns"]}
    assert columns["id"]["inferred_type"] == "integer"
    assert columns["price"]["inferred_type"] == "float"
    assert columns["in_stock"]["inferred_type"] == "boolean"
    assert columns["added_on"]["inferred_type"] == "date"
    assert columns["name"]["inferred_type"] == "string"


def test_column_mapping_updates_and_reports_available_analyses(client: TestClient) -> None:
    user = _register(client, "mapping@example.com")
    upload = _upload_csv(client, user["access_token"]).json()
    columns = client.get(
        f"/datasets/{upload['id']}/columns", headers=_auth_headers(user["access_token"])
    ).json()["columns"]
    id_column = next(c for c in columns if c["normalized_name"] == "id")
    price_column = next(c for c in columns if c["normalized_name"] == "price")

    response = client.patch(
        f"/datasets/{upload['id']}/columns",
        headers=_auth_headers(user["access_token"]),
        json={
            "columns": [
                {"column_id": id_column["id"], "mapped_business_field": "product_id"},
                {"column_id": price_column["id"], "mapped_business_field": "unit_cost"},
            ]
        },
    )

    assert response.status_code == 200
    body = response.json()
    mapped = {c["normalized_name"]: c["mapped_business_field"] for c in body["columns"]}
    assert mapped["id"] == "product_id"
    assert mapped["price"] == "unit_cost"
    # Margin analysis needs unit_cost + retail_price; only unit_cost is
    # mapped here, so it should NOT yet be available.
    assert "Margin analysis" not in body["available_analyses"]


def test_dataset_ownership_isolation(client: TestClient) -> None:
    owner = _register(client, "owner@example.com")
    other = _register(client, "other@example.com")
    upload = _upload_csv(client, owner["access_token"]).json()

    response = client.get(f"/datasets/{upload['id']}", headers=_auth_headers(other["access_token"]))

    assert response.status_code == 404


def test_unauthorized_access_rejected(client: TestClient) -> None:
    assert client.get("/datasets").status_code == 401

    upload_response = client.post("/datasets/upload", files={"file": ("a.csv", b"a,b\n1,2\n")})
    assert upload_response.status_code == 401


def test_dataset_deletion(client: TestClient) -> None:
    user = _register(client, "delete-me@example.com")
    upload = _upload_csv(client, user["access_token"]).json()
    headers = _auth_headers(user["access_token"])

    delete_response = client.delete(f"/datasets/{upload['id']}", headers=headers)
    assert delete_response.status_code == 204

    get_response = client.get(f"/datasets/{upload['id']}", headers=headers)
    assert get_response.status_code == 404

    list_response = client.get("/datasets", headers=headers)
    assert upload["id"] not in [d["id"] for d in list_response.json()]


async def test_failed_ingestion_leaves_no_orphaned_file(
    client: TestClient, db_session: AsyncSession
) -> None:
    from sqlalchemy import select

    from app.models.dataset import Dataset, DatasetStatus
    from app.services import storage

    user = _register(client, "rollback@example.com")

    response = _upload_csv(
        client, user["access_token"], content=MALFORMED_CSV, filename="rollback.csv"
    )
    assert response.status_code == 400

    # The dataset row still exists (status=failed) so the failure is
    # visible/auditable in the DB, but the on-disk file it briefly wrote
    # must have been removed - confirming no abandoned file was left
    # behind, and no dataset was left in an inconsistent (e.g. "ready"
    # with a missing file) state.
    result = await db_session.execute(
        select(Dataset)
        .where(Dataset.owner_user_id == uuid.UUID(user["user"]["id"]))
        .order_by(Dataset.created_at.desc())
    )
    dataset = result.scalars().first()
    assert dataset is not None
    assert dataset.status == DatasetStatus.FAILED
    assert dataset.error_message

    on_disk_path = storage.resolve_storage_path(dataset.storage_path)
    assert not on_disk_path.exists()
