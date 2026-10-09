# Account-free VM examples

These **v0.4.0 development examples** demonstrate importing, inspecting and exporting the six supported provider/OS recipes. They use synthetic account references and demonstration public keys. They are not deployment-ready, do not establish live compatibility and must not be applied as provided. No corresponding private key is supplied; the sample keys cannot provide usable guest access.

Use development main or a reviewed development commit. The released v0.3.0 package does not accept the `0.4.0.dev0` template label.

| Provider | Linux | Windows |
| --- | --- | --- |
| AWS | [Linux example](aws-linux.project.json) | [Windows example](aws-windows.project.json) |
| Azure | [Linux example](azure-linux.project.json) | [Windows example](azure-windows.project.json) |
| Google Cloud | [Linux example](gcp-linux.project.json) | [Windows example](gcp-windows.project.json) |

All examples use private VM recipes, no custom image, no initialization and no optional data disk. Omitted inputs resolve through documented recipe defaults; inspect those effective values rather than assuming the small example file contains every setting. No Spot/preemptible capacity is configured.

From the repository root:

```text
terraforma project-inputs --spec examples/vm/aws-linux.project.json
terraforma describe --spec examples/vm/aws-linux.project.json
terraforma generate --spec examples/vm/aws-linux.project.json --dir aws-linux-preview
```

Use a fresh output directory for each generation. These commands do not authenticate, plan or provision. The browser's project-import workflow can open the same specifications for review and download.

Azure Windows explicitly references `TF_VAR_admin_password` without providing its value. Generation needs no password; future planning/deployment requires an external credential and protected state. AWS Windows recovery and Google Windows guest account setup remain separate authenticated workflows. Google Windows is unavailable in the unupgraded Free Trial.

Before any live use, replace synthetic targets and demonstration keys, review every effective default, authenticate the intended target, verify images/sizes/quotas and establish spending, state and guest-access arrangements. Private VMs need a separately reviewed network path for administration. Follow [VM acceptance](../../docs/VM_ACCEPTANCE.md); examples never grant authorization to run cloud operations.
