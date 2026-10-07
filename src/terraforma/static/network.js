"use strict";

function vmPrivateAddressRange(provider, publicAccess, cidr) {
  if (!["aws", "azure", "gcp"].includes(provider) || typeof publicAccess !== "boolean" || typeof cidr !== "string") return null;
  const parts = cidr.split("/");
  if (parts.length !== 2 || !/^(16|17|18|19|20|21|22|23|24|25|26|27|28)$/.test(parts[1])) return null;
  const prefix = Number(parts[1]);
  if (provider !== "gcp" && prefix > 20) return null;
  const octets = parts[0].split(".");
  if (octets.length !== 4 || octets.some((value) => !/^(0|[1-9][0-9]{0,2})$/.test(value) || Number(value) > 255)) return null;
  const values = octets.map(Number);
  if (!(values[0] === 10 || (values[0] === 172 && values[1] >= 16 && values[1] <= 31) || (values[0] === 192 && values[1] === 168))) return null;
  let start = values.reduce((total, value) => total * 256 + value, 0);
  if (start % (2 ** (32 - prefix)) !== 0) return null;
  const subnetPrefix = provider === "gcp" ? prefix : prefix + 8;
  const size = 2 ** (32 - subnetPrefix);
  if (provider !== "gcp") start += size * (provider === "azure" ? 1 : publicAccess ? 0 : 10);
  const format = (value) => [24, 16, 8, 0].map((shift) => Math.floor(value / (2 ** shift)) % 256).join(".");
  return {
    subnet: `${format(start)}/${subnetPrefix}`,
    first: format(start + (provider === "gcp" ? 2 : 4)),
    last: format(start + size - (provider === "gcp" ? 3 : 2)),
  };
}
