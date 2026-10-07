import itertools

import pytest

from terraforma.generator import WizardConfig
from terraforma.guidance import infrastructure_guide


@pytest.mark.parametrize(
    "provider,workload",
    list(
        itertools.product(
            ["aws", "azure", "gcp"],
            ["single_web_server", "load_balanced_tier", "secure_database", "static_site"],
        )
    ),
)
def test_every_supported_workload_has_a_resource_guide(provider, workload):
    config = WizardConfig(provider=provider, project_name="example", architecture_type=workload)
    guide = infrastructure_guide(config)
    assert len(guide["route"]) == 3
    assert guide["route"][0] == "Private / authenticated access"
    assert len(guide["components"]) >= 3
    assert all(item["name"] and item["explanation"] for item in guide["components"])
