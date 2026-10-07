import itertools

import hcl2
import pytest
from fastapi.testclient import TestClient

from terraforma.generator import TerraformGenerator, WizardConfig
from terraforma.project import ProjectInputError, compile_project, input_contract
from terraforma.web import create_app
from tests.test_aws_placement import specification


@pytest.mark.parametrize(
    "windows,public,mode",
    list(
        itertools.product([False, True], [False, True], ["provider_default", "one_hop", "two_hops"])
    ),
)
def test_hop_choice_preserves_imdsv2_and_supported_mapping(windows, public, mode):
    spec = specification(windows, metadata_hop_limit=mode)
    spec.recipe.is_public = public
    result = compile_project(spec)
    main = hcl2.loads(result["files"]["main.tf"])
    instance = next(
        item['"aws_instance"']['"web"'] for item in main["resource"] if '"aws_instance"' in item
    )
    metadata = instance["metadata_options"][0]
    assert metadata["http_tokens"] == '"required"'
    assert '"provider_default" = null' in metadata["http_put_response_hop_limit"]
    assert '"one_hop" = 1' in metadata["http_put_response_hop_limit"]
    assert '"two_hops" = 2' in metadata["http_put_response_hop_limit"]
    assert f'default = "{mode}"' in result["files"]["variables.tf"]


@pytest.mark.parametrize("value", [0, 1, 2, True, "64", "three_hops", '${file("secret")}'])
def test_unsupported_hops_fail_closed(value):
    with pytest.raises(ProjectInputError) as error:
        compile_project(specification(False, metadata_hop_limit=value))
    assert error.value.field == "metadata_hop_limit"


@pytest.mark.parametrize(
    "provider,workload",
    [
        ("azure", "virtual_machine"),
        ("gcp", "windows_virtual_machine"),
        ("aws", "single_web_server"),
        ("aws", "load_balanced_tier"),
    ],
)
def test_only_aws_standalone_offers_hop_control(provider, workload):
    config = WizardConfig(
        provider=provider, project_name="metadata-scope", architecture_type=workload
    )
    assert "metadata_hop_limit" not in {item["name"] for item in input_contract(config)}
    if provider == "aws":
        assert 'http_tokens = "required"' in TerraformGenerator(config).generate()["main.tf"]


def test_import_preserves_unmanaged_default_and_explicit_choice():
    spec = specification(False, metadata_hop_limit="two_hops")
    contract = {item["name"]: item for item in input_contract(spec.recipe)}
    assert contract["metadata_hop_limit"]["default"] == "provider_default"
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        imported = client.post("/api/projects/import", json=spec.model_dump(), headers=headers)
        generated = client.post("/api/generate", json=spec.model_dump(), headers=headers)
    assert imported.status_code == generated.status_code == 200
    assert imported.json()["files"] == generated.json()["files"]
    choice = next(
        item for item in generated.json()["choice_summary"] if item["name"] == "metadata_hop_limit"
    )
    assert choice["value"] == "Two hops (container networking)"
