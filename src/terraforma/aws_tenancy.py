def declare_aws_tenancy(builder):
    builder.variable(
        "instance_tenancy",
        "EC2 hardware tenancy for this standalone VM. provider_default leaves instance tenancy unmanaged and uses provider/VPC behavior; an existing dedicated-tenancy VPC can enforce dedicated placement. dedicated requests hardware dedicated to your AWS account, with additional regional and instance charges. Other instances in the same account can share that hardware; EBS storage is not dedicated. Dedicated Instances do not select a host or establish BYOL eligibility. Verify selected size, region, licensing and capacity separately; the metadata preflight does not check tenancy support. Changes can require stopping or replacing the VM. Returning to provider_default does not reset an existing VM's effective tenancy. Dedicated Hosts and host affinity are unsupported.",
        "provider_default",
        choices=("provider_default", "dedicated"),
    )


def aws_tenancy_guidance(inputs):
    if inputs.get("instance_tenancy", "provider_default") == "dedicated":
        return "Dedicated Instance tenancy is requested for the VM, with additional charges. This does not allocate a Dedicated Host, isolate EBS storage or establish BYOL eligibility. Size/region support, capacity, licensing and effective placement remain unverified. Review stopping/replacement, boot-data preservation and the Terraform plan before changing tenancy."
    return "Instance tenancy is left unmanaged. Provider/VPC behavior determines effective placement; an existing dedicated-tenancy VPC can enforce dedicated placement. Returning to this option does not reset an existing VM's tenancy. Effective placement and tenancy compatibility remain unverified."
