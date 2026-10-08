import hashlib
import json

import pytest
from click.testing import CliRunner
from pydantic import ValidationError

from terraforma.backend import MAX_BACKEND_BYTES, load_and_review_backend, review_backend
from terraforma.cli import main


def intent(backend):
    common = {"schema_version": 1, "owner": "private-team", "environment": "production"}
    choices = {
        "s3": {
            "account_id": "123456789012",
            "bucket": "private-state-bucket",
            "region": "us-east-1",
            "key": "production/network/terraform.tfstate",
            "use_lockfile": True,
        },
        "azurerm": {
            "tenant_id": "11111111-1111-4111-8111-111111111111",
            "subscription_id": "22222222-2222-4222-8222-222222222222",
            "storage_account_name": "privatestatestorage",
            "container_name": "private-state",
            "key": "production/network/terraform.tfstate",
        },
        "gcs": {
            "project_id": "private-state-project",
            "bucket": "private-state-bucket",
            "prefix": "production/network",
        },
    }
    return {**common, "backend": backend, **choices[backend]}


@pytest.mark.parametrize("backend", ["s3", "azurerm", "gcs"])
def test_valid_intent_is_offline_unverified_and_omits_locations(backend, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Backend input checking must not contact a cloud or run Terraform.")

    monkeypatch.setattr("subprocess.run", forbidden)
    monkeypatch.setattr("socket.create_connection", forbidden)
    raw = json.dumps(intent(backend)).encode()
    report = review_backend(raw)
    assert report["backend"] == backend
    assert report["artifact_sha256"] == hashlib.sha256(raw).hexdigest()
    assert report["status"] == "inputs_valid_verification_required"
    assert report["backend_configured"] is False
    assert report["identity_verified"] is False
    assert report["approval_granted"] is False
    assert "private-" not in json.dumps(report)


@pytest.mark.parametrize("backend", ["s3", "azurerm", "gcs"])
@pytest.mark.parametrize("field", ["credentials", "access_key", "client_secret", "token"])
def test_credentials_are_not_accepted(backend, field):
    data = {**intent(backend), field: "private-secret"}
    with pytest.raises(ValidationError):
        review_backend(json.dumps(data).encode())


@pytest.mark.parametrize(
    "backend,field,value",
    [
        ("s3", "use_lockfile", False),
        ("s3", "use_lockfile", 1),
        ("s3", "use_lockfile", "true"),
        ("s3", "account_id", 123456789012),
        ("s3", "account_id", "1234"),
        ("s3", "region", "https://private-endpoint"),
        ("s3", "bucket", "xn--private-bucket"),
        ("s3", "bucket", "private--x-s3"),
        ("s3", "bucket", "private--table-s3"),
        ("s3", "bucket", "private-regional-an"),
        ("s3", "bucket", "127.0.0.1"),
        ("gcs", "bucket", "google-private-bucket"),
        ("gcs", "bucket", "g00gle-private-bucket"),
        ("gcs", "bucket", "PrivateBucket"),
        ("gcs", "bucket", "a" * 64),
        ("gcs", "project_id", "projects/private-project"),
        ("azurerm", "tenant_id", "not-a-uuid"),
        ("azurerm", "subscription_id", "22222222222242228222222222222222"),
        ("azurerm", "storage_account_name", "private-storage"),
        ("azurerm", "container_name", "private--state"),
        ("s3", "schema_version", True),
        ("gcs", "schema_version", 2),
        ("azurerm", "owner", "private\nowner"),
        ("gcs", "environment", "Production"),
    ],
)
def test_unsupported_or_ambiguous_values_rejected(backend, field, value):
    data = {**intent(backend), field: value}
    with pytest.raises(ValidationError):
        review_backend(json.dumps(data).encode())


@pytest.mark.parametrize("backend,field", [("s3", "key"), ("azurerm", "key"), ("gcs", "prefix")])
@pytest.mark.parametrize(
    "value", ["", "/state", "../state", "env/./state", "a//b", "a\\b", "a" * 513]
)
def test_object_locations_are_bounded_relative_and_unambiguous(backend, field, value):
    with pytest.raises(ValidationError):
        review_backend(json.dumps({**intent(backend), field: value}).encode())


@pytest.mark.parametrize("backend", ["s3", "azurerm", "gcs"])
def test_required_fields_cannot_be_omitted(backend):
    data = intent(backend)
    for field in data:
        if field == "schema_version":
            continue
        with pytest.raises(ValidationError):
            review_backend(
                json.dumps({key: value for key, value in data.items() if key != field}).encode()
            )


@pytest.mark.parametrize(
    "raw",
    [
        b'{"backend":"s3","backend":"gcs"}',
        b'{"schema_version":NaN}',
        b"[]",
        b"\xff",
        b" " * (MAX_BACKEND_BYTES + 1),
    ],
)
def test_invalid_json_and_oversized_input_rejected(raw):
    with pytest.raises(ValueError):
        review_backend(raw)


@pytest.mark.parametrize("backend", ["s3", "azurerm", "gcs"])
def test_cli_report_matches_api_function_without_writing_configuration(tmp_path, backend):
    path = tmp_path / "backend.json"
    raw = json.dumps(intent(backend)).encode()
    path.write_bytes(raw)
    result = CliRunner().invoke(main, ["check-backend", "--file", str(path), "--json-output"])
    assert result.exit_code == 0
    assert json.loads(result.output) == review_backend(raw)
    assert path.read_bytes() == raw
    assert list(tmp_path.iterdir()) == [path]
    text_result = CliRunner().invoke(main, ["check-backend", "--file", str(path)])
    assert "No backend was configured" in text_result.output


def test_cli_failure_omits_private_values(tmp_path):
    path = tmp_path / "backend.json"
    path.write_text(json.dumps({**intent("s3"), "token": "private-secret"}))
    result = CliRunner().invoke(main, ["check-backend", "--file", str(path)])
    assert result.exit_code != 0
    assert "private-" not in result.output
    assert "input values are omitted" in result.output


def test_file_loader_rejects_directory_and_oversized_file(tmp_path):
    with pytest.raises((OSError, ValueError)):
        load_and_review_backend(tmp_path)
    path = tmp_path / "backend.json"
    path.write_bytes(b" " * (MAX_BACKEND_BYTES + 1))
    with pytest.raises(ValueError):
        load_and_review_backend(path)
