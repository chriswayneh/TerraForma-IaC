import json

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from terraforma.cli import main
from terraforma.plan_review import review_plan
from terraforma.web import create_app
from tests.test_plan_review import plan

KEY = "projects/private-key-project/locations/global/keyRings/private-ring/cryptoKeys/private-key"


def key_plan(vm, settings, before=None, markers=False, actions=None):
    field = "boot_disk" if vm else "disk_encryption_key"
    data = plan(
        "google_compute_instance" if vm else "google_compute_disk", {field: settings}, actions
    )
    change = data["resource_changes"][0]["change"]
    change["after_unknown"] = {field: markers}
    if before is not None:
        change["before"] = {field: before}
    return data


def findings(data):
    report = review_plan(data, artifact_sha256="test")
    assert report["policy_version"] == "0.11.0"
    assert report["approval_granted"] is False
    assert "private-key" not in json.dumps(report)
    return {item["code"]: item for item in report["findings"]}


@pytest.mark.parametrize("vm", [False, True])
def test_reference_requires_access_review_without_approving_encryption(vm):
    result = findings(key_plan(vm, [{"kms_key_self_link": KEY}]))
    assert result["disk_key_access_unverified"]["severity"] == "review"
    assert "disk_encryption_key_changed" not in result
    assert "limited_policy_coverage" in result


@pytest.mark.parametrize("vm", [False, True])
@pytest.mark.parametrize("previous,current", [(KEY, ""), ("", KEY), (KEY, KEY + "-different")])
def test_key_changes_block_even_without_resource_replacement(vm, previous, current):
    result = findings(
        key_plan(
            vm,
            [{"kms_key_self_link": current}],
            [{"kms_key_self_link": previous}],
            actions=["update"],
        )
    )
    assert result["disk_encryption_key_changed"]["severity"] == "block"


@pytest.mark.parametrize("vm", [False, True])
def test_same_key_does_not_claim_migration(vm):
    result = findings(
        key_plan(vm, [{"kms_key_self_link": KEY}], [{"kms_key_self_link": KEY}], actions=["update"])
    )
    assert "disk_encryption_key_changed" not in result
    assert "disk_key_access_unverified" in result


@pytest.mark.parametrize(
    "vm,field",
    [(True, "disk_encryption_key_raw"), (False, "raw_key"), (False, "rsa_encrypted_key")],
)
def test_inline_key_material_blocks_without_disclosing_it(vm, field):
    data = key_plan(vm, [{field: "private-raw-material"}])
    result = findings(data)
    assert result["inline_disk_key_material"]["severity"] == "block"
    assert "private-raw-material" not in json.dumps(review_plan(data, artifact_sha256="test"))


@pytest.mark.parametrize("vm", [False, True])
@pytest.mark.parametrize("markers", [True, [{"kms_key_self_link": True}]])
def test_unknown_key_controls_do_not_look_verified(vm, markers):
    result = findings(key_plan(vm, [{"kms_key_self_link": KEY}], markers=markers))
    assert "disk_encryption_key_unknown" in result
    assert "disk_key_access_unverified" not in result


@pytest.mark.parametrize(
    "vm,field",
    [(True, "disk_encryption_key_raw"), (False, "raw_key"), (False, "rsa_encrypted_key")],
)
@pytest.mark.parametrize("new_key", ["", KEY])
def test_removed_key_material_still_requires_protected_plan_review(vm, field, new_key):
    data = key_plan(
        vm,
        [{"kms_key_self_link": new_key}],
        [{field: "private-prior-key-material"}],
        actions=["update"],
    )
    result = findings(data)
    assert result["inline_disk_key_material"]["severity"] == "block"
    assert "private-prior-key-material" not in json.dumps(review_plan(data, artifact_sha256="test"))


@pytest.mark.parametrize("vm", [False, True])
def test_unrelated_unknown_id_keeps_key_access_review(vm):
    result = findings(key_plan(vm, [{"kms_key_self_link": KEY}], markers=[{"id": True}]))
    assert "disk_key_access_unverified" in result


@pytest.mark.parametrize("vm", [False, True])
@pytest.mark.parametrize(
    "settings", [None, [], [{}], [{"kms_key_self_link": None}], [{"kms_key_self_link": ""}]]
)
def test_absent_key_is_not_reported_as_unencrypted(vm, settings):
    result = findings(key_plan(vm, settings))
    assert "disk_key_access_unverified" not in result
    assert "inline_disk_key_material" not in result
    assert "unencrypted_disk" not in result


@pytest.mark.parametrize("vm", [False, True])
@pytest.mark.parametrize(
    "settings",
    [
        True,
        {},
        [True],
        [{}, {}],
        [{"kms_key_self_link": True}],
        [{"kms_key_self_link": []}],
        [{"kms_key_self_link": "x" * 4097}],
    ],
)
def test_malformed_controls_fail_closed(vm, settings):
    assert findings(key_plan(vm, settings))["unresolved_policy_input"]["severity"] == "block"


@pytest.mark.parametrize("vm", [False, True])
@pytest.mark.parametrize(
    "markers", [None, 0, "private-marker", [True], [{}, {}], [{"kms_key_self_link": None}]]
)
def test_malformed_unknown_markers_fail_closed(vm, markers):
    data = key_plan(vm, [{"kms_key_self_link": KEY}], markers=markers)
    assert "unresolved_policy_input" in findings(data)
    assert "private-marker" not in json.dumps(review_plan(data, artifact_sha256="test"))


def test_destructive_block_remains_present_with_key_reference():
    assert "destructive_change" in findings(
        key_plan(False, [{"kms_key_self_link": KEY}], actions=["delete", "create"])
    )


@pytest.mark.parametrize("raw_material", [False, True])
def test_cli_api_return_identical_private_value_free_reports(tmp_path, raw_material):
    settings = (
        [{"raw_key": "private-raw-material"}] if raw_material else [{"kms_key_self_link": KEY}]
    )
    raw = json.dumps(key_plan(False, settings)).encode()
    path = tmp_path / "plan.json"
    path.write_bytes(raw)
    result = CliRunner().invoke(main, ["review-plan", "--file", str(path), "--json-output"])
    assert result.exit_code == (1 if raw_material else 0)
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        token = client.get("/api/session").json()["token"]
        response = client.post(
            "/api/plans/review", headers={"X-TerraForma-Token": token}, content=raw
        )
    assert response.status_code == 200
    assert json.loads(result.output) == response.json()
    assert "private-" not in result.output
