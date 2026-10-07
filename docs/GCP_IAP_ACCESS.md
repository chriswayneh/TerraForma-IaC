# Google IAP administrator access

On development `main`, standalone GCP Linux and Windows recipes offer **Administrator connection path**. Choose `iap_tunnel` to generate one targeted TCP firewall rule for Google's IPv4 IAP proxy range. The direct administrator network question is hidden because that value is unused by the tunnel rule. The default `administrator_network` choice preserves direct access and its existing restrictions.

IAP can connect to a VM without an external IP. Keep **Public internet access** off for a private VM; choosing IAP does not change that separate setting. Linux uses SSH port 22 with OS Login; Windows uses RDP port 3389 with separately configured guest credentials. The recipe creates no tunnel IAM binding, guest account or connection. Existing cloud setup and access permissions remain required. Review [Google's IAP TCP forwarding setup](https://docs.cloud.google.com/iap/docs/using-tcp-forwarding) before provisioning.

Tunnel authorization and guest authentication are separate. An administrator must review the appropriate `roles/iap.tunnelResourceAccessor` grant, Compute permissions, OS Login roles for Linux and service-account attachment requirements where applicable. Scope access to the intended VM and port. A firewall network tag selects packets; it does not scope IAP IAM. Check other firewall rules and organization policy for alternate access paths. TerraForma does not inspect or grant these permissions.

After separately reviewed provisioning and access setup, replace the example names with the generated VM name, project ID and zone. These commands open a connection; TerraForma does not run them.

Linux, using [gcloud compute ssh](https://docs.cloud.google.com/sdk/gcloud/reference/compute/ssh):

```text
gcloud compute ssh demo-vm --project=example-project --zone=us-central1-a --tunnel-through-iap
```

Windows, using [gcloud compute start-iap-tunnel](https://docs.cloud.google.com/sdk/gcloud/reference/compute/start-iap-tunnel):

```text
gcloud compute start-iap-tunnel demo-vm 3389 --project=example-project --zone=us-central1-a --local-host-port=localhost:13389
```

Keep the tunnel process running and connect an RDP client to `localhost:13389` with the guest credentials established separately. Choose another unused local port if needed. This example binds to localhost. Close the tunnel when finished. Review the [Windows credential guidance](WINDOWS_VM.md) before resetting an existing password.

Changing the access method updates the firewall and can interrupt access. Returning to direct access requires a reviewed administrator CIDR and routed path; public-mode direct access requires an explicit CIDR answer. The unused Terraform CIDR variable has a private fallback when compiling an IAP project without an answer. Regenerate with the new choice rather than assuming the tunnel grants or removes IAM permissions. Local policy recognizes an exact targeted IAP rule as mandatory manual review; broader or unresolved administrator rules remain blocked. No report approves deployment.

Terraform validation and TFLint cover generated configuration locally. Live IAP authorization, SSH/RDP connectivity, guest authentication, capacity and teardown remain unverified. IPv6 IAP, existing-network attachments and automated access management are outside this initial option.
