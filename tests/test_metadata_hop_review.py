import json

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from terraforma.cli import main
from terraforma.plan_review import review_plan
from terraforma.web import create_app
from tests.test_plan_review import plan


def metadata_plan(hops=1, endpoint="enabled", tokens="required", markers=False):
    data = plan(
        "aws_instance",
        {
            "metadata_options": [
                {
                    "http_endpoint": endpoint,
                    "http_tokens": tokens,
                    "http_put_response_hop_limit": hops,
                }
            ],
            "root_block_device": [{"encrypted": True}],
        },
    )
    data["resource_changes"][0]["change"]["after_unknown"] = {"metadata_options": markers}
    return data


def report(data):
    result = review_plan(data, artifact_sha256="test")
    assert result["approval_granted"] is False
    assert result["policy_version"] == "0.10.0"
    return {item["code"]: item for item in result["findings"]}


@pytest.mark.parametrize("hops", [2, 3, 64])
def test_extra_hops_require_manual_review(hops):
    findings = report(metadata_plan(hops))
    assert findings["instance_metadata_extra_hops"]["severity"] == "review"
    assert "instance_metadata_hops_unknown" not in findings


@pytest.mark.parametrize("hops", [1, 2, 64, None])
def test_known_disabled_endpoint_has_no_hop_exposure(hops):
    findings = report(metadata_plan(hops, endpoint="disabled"))
    assert "instance_metadata_extra_hops" not in findings
    assert "instance_metadata_hops_unknown" not in findings


def test_one_hop_remains_partial_manual_review():
    findings = report(metadata_plan())
    assert "instance_metadata_extra_hops" not in findings
    assert "instance_metadata_hops_unknown" not in findings
    assert "limited_policy_coverage" in findings


@pytest.mark.parametrize(
    "markers", [True, [{"http_put_response_hop_limit": True}], [{"http_endpoint": True}]]
)
@pytest.mark.parametrize("endpoint", ["enabled", "disabled"])
def test_unknown_relevant_controls_cannot_look_established(markers, endpoint):
    findings = report(metadata_plan(2, endpoint=endpoint, markers=markers))
    if endpoint == "disabled" and markers == [{"http_put_response_hop_limit": True}]:
        assert "instance_metadata_hops_unknown" not in findings
    else:
        assert "instance_metadata_hops_unknown" in findings
    assert "instance_metadata_extra_hops" not in findings


@pytest.mark.parametrize("hops", [None, "2", True, False, 0, 65, 2.0, [], {}])
def test_missing_or_malformed_hops_require_review(hops):
    findings = report(metadata_plan(hops))
    assert (
        "instance_metadata_hops_unknown" in findings
        if hops is None
        else "unresolved_policy_input" in findings
    )


@pytest.mark.parametrize(
    "markers",
    [
        None,
        "private-marker",
        0,
        [],
        [True],
        [{}, {}],
        [{"http_endpoint": None}],
        [{"http_put_response_hop_limit": "private-marker"}],
    ],
)
def test_malformed_unknown_markers_fail_closed_and_remain_private(markers):
    data = metadata_plan(markers=markers)
    assert "unresolved_policy_input" in report(data)
    assert "private-marker" not in json.dumps(review_plan(data, artifact_sha256="test"))


def test_unrelated_unknown_id_does_not_hide_hop_review():
    assert "instance_metadata_extra_hops" in report(metadata_plan(2, markers=[{"id": True}]))


def test_legacy_metadata_block_is_preserved_with_malformed_hops():
    findings = report(metadata_plan("invalid", tokens="optional"))
    assert findings["legacy_instance_metadata"]["severity"] == "block"
    assert "unresolved_policy_input" in findings


def test_cli_api_use_identical_redacted_policy(tmp_path):
    raw = json.dumps(metadata_plan(2)).encode()
    path = tmp_path / "plan.json"
    path.write_bytes(raw)
    result = CliRunner().invoke(main, ["review-plan", "--file", str(path), "--json-output"])
    assert result.exit_code == 0
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        token = client.get("/api/session").json()["token"]
        response = client.post(
            "/api/plans/review", headers={"X-TerraForma-Token": token}, content=raw
        )
    assert response.status_code == 200
    assert json.loads(result.output) == response.json()
    assert "private-secret-key" not in result.output
