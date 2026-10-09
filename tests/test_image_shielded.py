import json

import pytest

from terraforma.preflight import target_preflight
from tests.test_custom_images import specification
from tests.test_image_preflight import image_records, mocks


@pytest.mark.parametrize("windows", [False, True])
@pytest.mark.parametrize("custom", [False, True])
@pytest.mark.parametrize("secure_boot", [False, True])
@pytest.mark.parametrize("uefi", [False, True, None])
def test_standalone_gcp_images_need_reported_shielded_firmware_even_with_secure_boot_off(
    windows, custom, secure_boot, uefi, monkeypatch
):
    spec = specification("gcp", windows=windows, custom=custom, enable_secure_boot=secure_boot)
    records = image_records(spec)
    records[0]["guestOsFeatures"] = (
        None
        if uefi is None
        else ([{"type": "WINDOWS"}] if windows else [])
        + ([{"type": "UEFI_COMPATIBLE"}] if uefi else [])
    )
    calls = mocks(monkeypatch, spec, records)
    report = target_preflight(spec, verify_target=True, verify_image=True)
    check = report["image_check"]
    assert check["shielded_firmware_compatible"] is uefi
    assert check["status"] == (
        "metadata_unknown" if uefi is None else "metadata_confirmed" if uefi else "incompatible"
    )
    assert len(calls) == 2
    assert report["approval_granted"] is False


@pytest.mark.parametrize(
    "features",
    [
        [{"type": "UEFI_COMPATIBLE"}, {"type": "UEFI_COMPATIBLE"}],
        [{"type": "WINDOWS"}, {"type": "WINDOWS"}],
        [{"type": ["private-marker"]}],
        ["private-marker"],
    ],
)
def test_malformed_or_duplicate_guest_feature_metadata_rejected(features, monkeypatch):
    spec = specification("gcp")
    records = image_records(spec)
    records[0]["guestOsFeatures"] = features
    mocks(monkeypatch, spec, records)
    report = target_preflight(spec, verify_target=True, verify_image=True)
    assert report["image_check"] == {"status": "invalid_response"}
    assert "private-marker" not in json.dumps(report)


def test_web_recipe_does_not_add_standalone_shielded_requirements(monkeypatch):
    from tests.test_machine_preflight import spec as web_spec

    spec = web_spec("gcp")
    records = image_records(spec)
    records[0]["guestOsFeatures"] = []
    mocks(monkeypatch, spec, records)
    check = target_preflight(spec, verify_target=True, verify_image=True)["image_check"]
    assert "shielded_firmware_compatible" not in check
    assert check["status"] == "metadata_confirmed"
