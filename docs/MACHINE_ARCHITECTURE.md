# VM machine architecture checks

TerraForma's current compute recipes require **x86-64 machines**. Supported Linux catalog images, Windows Server images and reviewed custom images use that architecture. Choosing an Arm size does not convert the image or enable an Arm recipe.

Development builds reject recognized Arm machine identifiers before generating files. The terminal questionnaire, saved-project compilation/import, browser API and optional Terragrunt export share this check. Generated Terraform also rejects the same identifiers when a variable is overridden later.

| Provider | Known Arm identifiers rejected offline | Reference |
|---|---|---|
| AWS | Documented Graviton families, including T4g; M6g–M9g, C6g–C9g and R6g–R9g variants listed in the current family tables; X2gd/X8g, I4g/I8g/I8ge/Im4gn/Is4gen and G5g; NVIDIA Grace P6e-GB200 | [General purpose](https://docs.aws.amazon.com/ec2/latest/instancetypes/gp.html), [compute optimized](https://docs.aws.amazon.com/ec2/latest/instancetypes/co.html), [memory optimized](https://docs.aws.amazon.com/ec2/latest/instancetypes/mo.html), [storage optimized](https://docs.aws.amazon.com/ec2/latest/instancetypes/so.html), [accelerated computing](https://docs.aws.amazon.com/ec2/latest/instancetypes/ac.html) |
| Azure | Standard size names containing the lowercase `p` CPU feature after the vCPU count, including constrained-vCPU forms | [Size naming conventions](https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/overview) |
| GCP | T2A, C4A, N4A and A4X prefixes, including A4X Max | [Arm on Compute](https://docs.cloud.google.com/compute/docs/instances/arm-on-compute) |

The AWS family list is a documented snapshot, not a rule that every name containing `g` is Arm. For example, G5 and G5g differ. Azure's AMD `a` and GCP's T2D/N4D names must not be confused with Arm. The check uses family boundaries so an unknown similarly named size is not automatically classified.

**A size that passes this guard remains unverified.** The guard does not establish that the identifier exists, that a region/account offers it, or that its image, disk, boot mode, quota, permissions or workload are compatible. New families may require an updated snapshot. The optional, separately authorized [machine/image preflight](IMAGE_PREFLIGHT.md) uses selected-account metadata; missing metadata remains unknown. Offline generation performs no cloud lookup.

Choose a supported x86-64 size after reviewing the provider's specifications and your workload requirements. Arm images, cross-architecture migration and Arm-specific disk/network adapters remain outside the current catalog. Existing deployed machines require their own change, replacement and recovery review.
