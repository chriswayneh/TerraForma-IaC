from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

LINUX_IMAGE_CHOICES = {
    "aws": ("amazon-linux-2023", "ubuntu-24.04"),
    "azure": ("ubuntu-22.04", "ubuntu-24.04"),
    "gcp": ("debian-12", "ubuntu-24.04"),
}

AZURE_RESERVED_USERNAMES = (
    "1",
    "123",
    "a",
    "actuser",
    "adm",
    "admin",
    "admin1",
    "admin2",
    "administrator",
    "aspnet",
    "backup",
    "console",
    "david",
    "guest",
    "john",
    "owner",
    "root",
    "server",
    "sql",
    "support_388945a0",
    "support",
    "sys",
    "test",
    "test1",
    "test2",
    "test3",
    "user",
    "user1",
    "user2",
    "user3",
    "user4",
    "user5",
    "video",
)


class WizardConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    provider: Literal["aws", "azure", "gcp"]
    project_name: str = Field(pattern="^[a-z][a-z0-9\\-]{1,18}[a-z0-9]$")
    architecture_type: Literal[
        "virtual_machine",
        "single_web_server",
        "load_balanced_tier",
        "secure_database",
        "static_site",
    ]
    is_public: bool = False
    enable_encryption: bool = True
