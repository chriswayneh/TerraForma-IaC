import copy
import hashlib
import json
from pathlib import Path

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from terraforma.cli import main
from terraforma.image_metadata import aws_catalog, azure_catalog, gcp_catalog, image_values
from terraforma.image_preflight import image_commands
from terraforma.preflight import target_preflight
from terraforma.process import CommandResult
from terraforma.web import create_app
from tests.test_custom_images import specification
from tests.test_preflight_web import headers


def image_records(spec):
    values = image_values(spec)
    provider = spec.recipe.provider
    custom = values.get("use_custom_image", False)
    windows = spec.recipe.architecture_type == "windows_virtual_machine"
    if provider == "aws":
        owner, pattern = aws_catalog(values["os_image"])
        return [
            {
                "Images": [
                    {
                        "ImageId": values["custom_image"] if custom else "ami-0123456789abcdef0",
                        "OwnerId": values["custom_image_owner_account_id"]
                        if custom
                        else "099720109477",
                        "ImageOwnerAlias": "amazon" if owner == "amazon" else None,
                        "Name": pattern.replace("*", "20261001"),
                        "State": "available",
                        "Architecture": "x86_64",
                        "Platform": "windows" if windows else None,
                        "RootDeviceType": "ebs",
                        "VirtualizationType": "hvm",
                        "RootDeviceName": "/dev/sda1",
                        "BlockDeviceMappings": [
                            {"DeviceName": "/dev/sda1", "Ebs": {"VolumeSize": 20}}
                        ],
                        "Public": False,
                        "ProductCodes": [],
                        "private-field": "private-marker",
                    }
                ]
            }
        ]
    if provider == "gcp":
        project, family, prefix = gcp_catalog(values["os_image"])
        if custom:
            project = values["custom_image"].split("/")[1]
        name = values["custom_image"].split("/")[-1] if custom else prefix + "20261001"
        return [
            {
                "name": name,
                "family": family,
                "selfLink": f"https://www.googleapis.com/compute/v1/projects/{project}/global/images/{name}",
                "status": "READY",
                "architecture": "X86_64",
                "diskSizeGb": "20",
                "guestOsFeatures": [{"type": "UEFI_COMPATIBLE"}]
                + ([{"type": "WINDOWS"}] if windows else []),
                "private-field": "private-marker",
            }
        ]
    if custom:
        return [
            {
                "id": values["custom_image"],
                "properties": {
                    "provisioningState": "Succeeded",
                    "replicationStatus": {"summary": [{"region": "East US", "state": "Completed"}]},
                    "storageProfile": {"osDiskImage": {"sizeInGB": 20}, "dataDiskImages": []},
                },
            },
            {
                "id": values["custom_image"].rsplit("/versions/", 1)[0],
                "properties": {
                    "architecture": "x64",
                    "osType": "Windows" if windows else "Linux",
                    "osState": "Generalized",
                    "hyperVGeneration": "V2",
                    "features": [{"name": "SecurityType", "value": "TrustedLaunchSupported"}],
                    "private-field": "private-marker",
                },
            },
        ]
    publisher, offer, sku = azure_catalog(values["os_image"])
    prefix = f"/subscriptions/{values['subscription_id']}/providers/Microsoft.Compute/locations/{values['location']}/publishers/{publisher}/artifacttypes/vmimage/offers/{offer}/skus/{sku}/versions/"
    return [
        {
            "id": prefix + "1.0.0",
            "name": "1.0.0",
            "properties": {
                "architecture": "x64",
                "hyperVGeneration": "V2",
                "osDiskImage": {"operatingSystem": "Windows" if windows else "Linux"},
                "dataDiskImages": [],
                "imageDeprecationStatus": {"imageState": "Active"},
                "private-field": "private-marker",
            },
        }
    ]


def mocks(monkeypatch, spec, records=None, *, target_matches=True, result=None):
    calls = []
    values = image_values(spec)
    target = {
        "aws": {"Account": values.get("aws_account_id") if target_matches else "999999999999"},
        "azure": {
            "subscriptionId": values.get("subscription_id")
            if target_matches
            else "99999999-9999-9999-9999-999999999999",
            "state": "Enabled",
        },
        "gcp": {
            "projectId": values.get("gcp_project_id") if target_matches else "other-project",
            "lifecycleState": "ACTIVE",
        },
    }[spec.recipe.provider]
    monkeypatch.setattr("terraforma.preflight.shutil.which", lambda name: "fake-cloud-cli")

    def target_run(arguments, **kwargs):
        calls.append((arguments, kwargs))
        return CommandResult(0, json.dumps(target).encode(), b"private-marker")

    responses = image_records(spec) if records is None else records

    def image_run(arguments, **kwargs):
        calls.append((arguments, kwargs))
        if isinstance(result, Exception):
            raise result
        if result is not None:
            return result
        return CommandResult(0, json.dumps(responses.pop(0)).encode(), b"private-marker")

    monkeypatch.setattr("terraforma.preflight.run_bounded", target_run)
    monkeypatch.setattr("terraforma.image_preflight.run_bounded", image_run)
    return calls


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
@pytest.mark.parametrize("windows", [False, True])
@pytest.mark.parametrize("custom", [False, True])
def test_image_metadata_is_bounded_private_and_never_approves_deployment(
    provider, windows, custom, monkeypatch
):
    spec = specification(provider, windows=windows, custom=custom)
    calls = mocks(monkeypatch, spec)
    report = target_preflight(spec, verify_target=True, verify_image=True)
    expected = "metadata_unknown" if provider == "azure" and not custom else "metadata_confirmed"
    assert report["image_check"]["status"] == expected
    assert len(calls) == (3 if provider == "azure" and custom else 2)
    assert report["approval_granted"] is False
    assert report["deployment_readiness_verified"] is False
    assert "private-marker" not in json.dumps(report)
    assert report["image_check"]["source_compatible"] is True
    assert len(report["image_check"]["resolved_reference_sha256"]) == 64
    for _, options in calls:
        assert options["timeout"] == 30
        assert options["stream_limit"] == 128 * 1024
        assert not Path(options["cwd"]).exists()
        assert options["env"]["AZURE_EXTENSION_USE_DYNAMIC_INSTALL"] == "no"


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
def test_image_reads_require_separate_consent_and_matching_target(provider, monkeypatch):
    spec = specification(provider)
    calls = mocks(monkeypatch, spec, target_matches=False)
    assert target_preflight(spec)["image_check"]["status"] == "not_checked"
    with pytest.raises(ValueError, match="consent"):
        target_preflight(spec, verify_image=True)
    assert calls == []
    assert target_preflight(spec, verify_target=True)["image_check"]["status"] == "not_checked"
    assert len(calls) == 1
    assert (
        target_preflight(spec, verify_target=True, verify_image=True)["status"] == "target_mismatch"
    )
    assert len(calls) == 2


@pytest.mark.parametrize("consent", [1, "true", None, [], {}])
def test_invalid_image_consent_rejected_before_execution(consent, monkeypatch):
    spec = specification("aws")
    calls = mocks(monkeypatch, spec)
    with pytest.raises(ValueError):
        target_preflight(spec, verify_target=True, verify_image=consent)
    assert calls == []


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
@pytest.mark.parametrize(
    "failure",
    [
        CommandResult(1, b"private-marker", b"private-marker"),
        CommandResult(0, b'{"private":"private-marker","private":2}', b""),
        CommandResult(0, b"[]", b"private-marker"),
        OSError("private-marker"),
    ],
)
def test_image_failures_never_disclose_raw_responses(provider, failure, monkeypatch):
    spec = specification(provider)
    calls = mocks(monkeypatch, spec, result=failure)
    report = target_preflight(spec, verify_target=True, verify_image=True)
    assert report["image_check"]["status"] in {"failed", "invalid_response"}
    assert len(calls) == 2
    assert "private-marker" not in json.dumps(report)


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
@pytest.mark.parametrize("field", ["architecture", "os", "source", "disk", "missing", "malformed"])
def test_custom_image_rejects_incompatible_and_unknown_metadata(provider, field, monkeypatch):
    spec = specification(provider)
    records = image_records(spec)
    if provider == "aws":
        image = records[0]["Images"][0]
        key = {
            "architecture": "Architecture",
            "os": "Platform",
            "source": "OwnerId",
            "missing": "Architecture",
            "malformed": "Architecture",
        }.get(field)
        if field == "disk":
            image["BlockDeviceMappings"][0]["Ebs"]["VolumeSize"] = 1000
        else:
            image[key] = {
                "architecture": "arm64",
                "os": "windows",
                "source": "999999999999",
                "missing": None,
                "malformed": ["private-marker"],
            }[field]
    elif provider == "gcp":
        image = records[0]
        image.update(
            {
                "architecture": {"architecture": "ARM64"},
                "os": {"guestOsFeatures": [{"type": "WINDOWS"}]},
                "source": {"selfLink": image["selfLink"].replace("image-library", "other-project")},
                "disk": {"diskSizeGb": "1000"},
                "missing": {"architecture": None},
                "malformed": {"architecture": ["private-marker"]},
            }[field]
        )
    else:
        definition = records[1]["properties"]
        if field == "disk":
            records[0]["properties"]["storageProfile"]["osDiskImage"]["sizeInGB"] = 1000
        elif field == "source":
            records[0]["id"] += "0"
        else:
            definition[
                {
                    "architecture": "architecture",
                    "os": "osType",
                    "missing": "architecture",
                    "malformed": "architecture",
                }[field]
            ] = {
                "architecture": "Arm64",
                "os": "Windows",
                "missing": None,
                "malformed": ["private-marker"],
            }[field]
    mocks(monkeypatch, spec, records)
    report = target_preflight(spec, verify_target=True, verify_image=True)
    assert report["image_check"]["status"] == {
        "missing": "metadata_unknown",
        "malformed": "invalid_response",
    }.get(field, "incompatible")
    assert "private-marker" not in json.dumps(report)


def test_cli_and_api_require_image_consent_and_preserve_unknown_exit_status(tmp_path, monkeypatch):
    spec = specification("azure", custom=False)
    path = tmp_path / "project.json"
    path.write_text(spec.model_dump_json(), encoding="utf-8")
    calls = mocks(monkeypatch, spec)
    runner = CliRunner()
    assert runner.invoke(main, ["preflight", "--spec", str(path), "--verify-image"]).exit_code == 2
    assert calls == []
    result = runner.invoke(
        main,
        ["preflight", "--spec", str(path), "--verify-image", "--verify-target", "--json-output"],
    )
    assert result.exit_code == 1
    assert json.loads(result.output)["image_check"]["boot_disk_compatible"] is None
    calls = mocks(monkeypatch, spec)
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        payload = {"specification": spec.model_dump(), "verify_target": True, "verify_image": True}
        assert client.post("/api/projects/preflight", json=payload).status_code == 403
        assert calls == []
        response = client.post("/api/projects/preflight", json=payload, headers=headers(client))
        assert response.status_code == 200
        assert response.json()["image_check"]["status"] == "metadata_unknown"


@pytest.mark.parametrize("value", [1, "true", None, {}])
def test_api_image_consent_is_strict(value, monkeypatch):
    spec = specification("aws")
    calls = mocks(monkeypatch, spec)
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        response = client.post(
            "/api/projects/preflight",
            headers=headers(client),
            json={
                "specification": spec.model_dump(),
                "verify_target": True,
                "verify_image": value,
            },
        )
        assert response.status_code == 422
    assert calls == []


def test_commands_use_declared_image_sources_and_no_pagination():
    aws = image_commands(specification("aws"), "aws")[0]
    assert "--no-paginate" in aws
    assert "NextToken: NextToken" in aws[-1]
    assert "Name=is-public,Values=false" in aws
    azure = image_commands(specification("azure"), "az")
    assert azure[0][azure[0].index("--expand") + 1] == "ReplicationStatus"
    assert azure[1][azure[1].index("--ids") + 1].endswith("/images/approved-image")
    gcp = image_commands(specification("gcp"), "gcloud")[0]
    assert gcp[gcp.index("--project") + 1] == "image-library"


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
def test_web_recipe_image_check_uses_recipe_defaults(provider, monkeypatch):
    from tests.test_machine_preflight import spec as web_spec

    spec = web_spec(provider)
    mocks(monkeypatch, spec)
    check = target_preflight(spec, verify_target=True, verify_image=True)["image_check"]
    assert check["source_compatible"] is True
    assert check["status"] == ("metadata_unknown" if provider == "azure" else "metadata_confirmed")


def test_gcp_single_letter_image_reference_remains_supported(monkeypatch):
    spec = specification("gcp", custom_image="projects/image-library/global/images/i")
    mocks(monkeypatch, spec)
    assert (
        target_preflight(spec, verify_target=True, verify_image=True)["image_check"]["status"]
        == "metadata_confirmed"
    )


@pytest.mark.parametrize("failure", ["timeout", "output_limit"])
def test_bounded_failure_stops_gallery_definition_read(failure, monkeypatch):
    spec = specification("azure")
    calls = mocks(
        monkeypatch, spec, result=CommandResult(0, b"private-marker", b"private-marker", failure)
    )
    check = target_preflight(spec, verify_target=True, verify_image=True)["image_check"]
    assert check == {"status": "failed"}
    assert len(calls) == 2


def test_aws_partial_selection_is_never_confirmed(monkeypatch):
    spec = specification("aws")
    records = image_records(spec)
    records[0]["NextToken"] = "private-marker"
    mocks(monkeypatch, spec, records)
    assert target_preflight(spec, verify_target=True, verify_image=True)["image_check"] == {
        "status": "selection_incomplete"
    }


def test_reference_digest_does_not_expose_image_identifier(monkeypatch):
    spec = specification("aws")
    mocks(monkeypatch, spec)
    check = target_preflight(spec, verify_target=True, verify_image=True)["image_check"]
    assert (
        check["resolved_reference_sha256"]
        == hashlib.sha256(spec.inputs["custom_image"].encode()).hexdigest()
    )
    assert spec.inputs["custom_image"] not in json.dumps(check)


@pytest.mark.parametrize(
    "provider,change,expected",
    [
        ("aws", "private", "incompatible"),
        ("aws", "product", "incompatible"),
        ("aws", "deprecated", "incompatible"),
        ("aws", "extra_disk", "incompatible"),
        ("aws", "platform_type", "invalid_response"),
        ("aws", "duplicate_disk", "invalid_response"),
        ("aws", "empty", "not_found"),
        ("gcp", "deprecated", "incompatible"),
        ("gcp", "bad_url", "invalid_response"),
        ("gcp", "missing_features", "metadata_unknown"),
        ("gcp", "bool_disk", "invalid_response"),
        ("azure", "replication", "incompatible"),
        ("azure", "missing_region", "metadata_unknown"),
        ("azure", "duplicate_region", "invalid_response"),
        ("azure", "security", "incompatible"),
        ("azure", "duplicate_security", "invalid_response"),
        ("azure", "specialized", "incompatible"),
        ("azure", "plan", "incompatible"),
        ("azure", "empty_plan", "metadata_unknown"),
        ("azure", "extra_disk", "incompatible"),
    ],
)
def test_image_specific_requirements(provider, change, expected, monkeypatch):
    spec = specification(provider)
    records = image_records(spec)
    if provider == "aws":
        image = records[0]["Images"][0]
        if change == "private":
            image["Public"] = True
        elif change == "product":
            image["ProductCodes"] = [{"ProductCodeId": "private-marker"}]
        elif change == "deprecated":
            image["DeprecationTime"] = "2099-01-01T00:00:00Z"
        elif change == "extra_disk":
            image["BlockDeviceMappings"].append(
                {"DeviceName": "/dev/sdb", "Ebs": {"VolumeSize": 20}}
            )
        elif change == "platform_type":
            image["Platform"] = ["private-marker"]
        elif change == "duplicate_disk":
            image["BlockDeviceMappings"] *= 2
        else:
            records[0]["Images"] = []
    elif provider == "gcp":
        records[0].update(
            {
                "deprecated": {"deprecated": {"state": "DEPRECATED"}},
                "bad_url": {"selfLink": "https://private-marker.example/images/test"},
                "missing_features": {"guestOsFeatures": None},
                "bool_disk": {"diskSizeGb": True},
            }[change]
        )
    else:
        props = records[0]["properties"]
        definition = records[1]["properties"]
        if change == "replication":
            props["replicationStatus"]["summary"][0]["state"] = "Failed"
        elif change == "missing_region":
            props["replicationStatus"]["summary"][0]["region"] = "West US"
        elif change == "duplicate_region":
            props["replicationStatus"]["summary"] *= 2
        elif change == "security":
            definition["features"][0]["value"] = "ConfidentialVMSupported"
        elif change == "duplicate_security":
            definition["features"] *= 2
        elif change == "specialized":
            definition["osState"] = "Specialized"
        elif change in {"plan", "empty_plan"}:
            definition["purchasePlan"] = {"name": "private-marker"} if change == "plan" else {}
        else:
            props["storageProfile"]["dataDiskImages"] = [{"lun": 0}]
    mocks(monkeypatch, spec, records)
    report = target_preflight(spec, verify_target=True, verify_image=True)
    assert report["image_check"]["status"] == expected
    assert "private-marker" not in json.dumps(report)


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
def test_pinned_catalog_commands_and_metadata(provider, monkeypatch):
    spec = specification(provider, custom=False)
    records = image_records(spec)
    version = {
        "aws": records[0].get("Images", [{}])[0].get("ImageId"),
        "azure": records[0].get("name"),
        "gcp": records[0].get("name"),
    }[provider]
    spec.inputs["image_version"] = version
    calls = mocks(monkeypatch, spec, records)
    report = target_preflight(spec, verify_target=True, verify_image=True)
    assert report["image_check"]["source_compatible"] is True
    assert any(version in argument for argument in calls[1][0])


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
@pytest.mark.parametrize("windows", [False, True])
def test_combined_checks_remain_within_four_read_budget(provider, windows, monkeypatch):
    from tests.test_machine_preflight import MACHINES

    spec = specification(provider, windows=windows)
    if provider == "aws":
        spec.inputs["availability_zone"] = "us-east-1b"
    calls = mocks(monkeypatch, spec)
    values = image_values(spec)
    target = {
        "aws": {"Account": values.get("aws_account_id")},
        "azure": {"subscriptionId": values.get("subscription_id"), "state": "Enabled"},
        "gcp": {"projectId": values.get("gcp_project_id"), "lifecycleState": "ACTIVE"},
    }[provider]
    machine = copy.deepcopy(MACHINES[provider])
    if provider == "aws":
        machine["InstanceTypes"][0]["InstanceType"] = values["instance_type"]
    elif provider == "gcp":
        machine["name"] = values["machine_type"]
    if provider == "azure":
        machine[0]["name"] = values["vm_size"]
        machine[0]["capabilities"].extend(
            [
                {"name": "HyperVGenerations", "value": "V2"},
                {"name": "TrustedLaunchDisabled", "value": "False"},
            ]
        )
    responses = [target, machine]
    if provider == "aws":
        responses.append(
            {
                "InstanceTypeOfferings": [
                    {
                        "InstanceType": values["instance_type"],
                        "LocationType": "availability-zone",
                        "Location": "us-east-1b",
                    }
                ]
            }
        )

    def run(arguments, **kwargs):
        calls.append((arguments, kwargs))
        return CommandResult(0, json.dumps(responses.pop(0)).encode(), b"private-marker")

    monkeypatch.setattr("terraforma.preflight.run_bounded", run)
    report = target_preflight(spec, verify_target=True, verify_machine=True, verify_image=True)
    assert report["machine_check"]["status"] == "metadata_confirmed"
    assert report["image_check"]["status"] == "metadata_confirmed"
    assert len(calls) == (3 if provider == "gcp" else 4)
    assert report["approval_granted"] is False


def test_static_recipe_does_not_trigger_image_reads(monkeypatch):
    from tests.test_machine_preflight import spec as other_spec

    spec = other_spec("aws", "static_site")
    calls = mocks(monkeypatch, spec, records=[])
    assert (
        target_preflight(spec, verify_target=True, verify_image=True)["image_check"]["status"]
        == "not_applicable"
    )
    assert len(calls) == 1


def test_azure_ambiguous_property_envelope_rejected(monkeypatch):
    spec = specification("azure")
    records = copy.deepcopy(image_records(spec))
    records[0]["replicationStatus"] = records[0]["properties"]["replicationStatus"]
    mocks(monkeypatch, spec, records)
    assert (
        target_preflight(spec, verify_target=True, verify_image=True)["image_check"]["status"]
        == "invalid_response"
    )
