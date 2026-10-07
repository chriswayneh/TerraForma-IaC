"use strict";

const byId = (id) => document.getElementById(id);
const form = byId("wizard-form");
const steps = [
  byId("cloud-step"),
  byId("workload-step"),
  byId("configure-step"),
];
let step = 0;
let token = "";
let busy = false;
let project = null;
let selectedFile = "main.tf";
let aiAvailable = false;
let contractKey = "";
let contract = [];
let templateVersion = "";

const inputSections = [
  ["Cloud target", ["environment", "aws_account_id", "subscription_id", "gcp_project_id", "region", "location", "zone"]],
  ["Image and capacity", ["os_image", "image_version", "instance_type", "vm_size", "machine_type", "instance_count", "computer_name", "license_type"]],
  ["Network and access", ["network_cidr", "private_ip_address", "allowed_cidr", "admin_username", "windows_username", "admin_password", "ssh_public_key", "client_ip"]],
  ["Storage", ["enable_data_disk", "data_disk_size_gb", "data_disk_type", "data_disk_iops", "data_disk_throughput", "data_disk_caching", "boot_disk_size_gb", "boot_disk_type", "boot_disk_iops", "boot_disk_throughput", "boot_disk_caching"]],
  ["Operations and identity", ["enable_workload_identity", "workload_identity", "detailed_monitoring", "protect_vm", "enable_secure_boot", "enable_boot_diagnostics", "enable_accelerated_networking", "enable_patch_assessment"]],
  ["Workload inputs", []],
];

function projectSpecification() {
  const inputs = {};
  const secret_references = {};
  contract.forEach((definition) => {
    if (definition.sensitive) {
      secret_references[definition.name] = definition.environment_variable;
    } else if (definition.editable) {
      const input = byId(`recipe-${definition.name}`);
      if (definition.visible_when && byId(`recipe-group-${definition.name}`).hidden) return;
      const value = definition.kind === "boolean" ? input.checked : input.value;
      inputs[definition.name] =
        definition.kind === "integer" ? Number(value) : value;
    }
  });
  return {
    schema_version: 1,
    template_version: templateVersion,
    recipe: configuration(),
    inputs,
    secret_references,
  };
}

async function loadRecipeInputs() {
  const config = configuration();
  const key = [
    config.provider,
    config.architecture_type,
    config.is_public,
  ].join(":");
  if (key === contractKey) return;
  const retained = {};
  if (
    contractKey.split(":").slice(0, 2).join(":") ===
    key.split(":").slice(0, 2).join(":")
  ) {
    contract.forEach((definition) => {
      const input = byId(`recipe-${definition.name}`);
      const value = input && (definition.kind === "boolean" ? input.checked : input.value);
      if (input && value !== (definition.default ?? ""))
        retained[definition.name] = value;
    });
  }
  const result = await (await api("/api/input-contract", config)).json();
  contract = result.inputs;
  templateVersion = result.template_version;
  byId("recipe-fixed-choices").replaceChildren(
    ...result.capabilities.fixed_choices.map((choice) => {
      const item = document.createElement("li");
      item.textContent = choice;
      return item;
    }),
  );
  byId("recipe-unsupported").textContent =
    "Not available in this recipe: " + result.capabilities.unsupported.join(", ") + ".";
  byId("recipe-capabilities").hidden = false;
  const container = byId("recipe-inputs");
  container.replaceChildren();
  const sections = new Map();
  contract.forEach((definition) => {
    if (!definition.editable) return;
    const group = document.createElement("div");
    group.id = `recipe-group-${definition.name}`;
    group.className = "recipe-input-group";
    const label = document.createElement("label");
    label.className = "input-label";
    label.textContent = definition.label;
    const help = document.createElement("p");
    help.className = "input-help";
    help.id = `recipe-help-${definition.name}`;
    if (definition.sensitive) {
      help.textContent = `${definition.description} Supply ${definition.environment_variable} through your environment before planning. Its value is not collected or saved here.`;
      group.append(label, help);
    } else {
      const input = document.createElement(
        definition.choices
          ? "select"
          : definition.kind === "multiline"
            ? "textarea"
            : "input",
      );
      input.id = `recipe-${definition.name}`;
      input.className = "text-input";
      if (definition.choices) {
        definition.choices.forEach((choice) => {
          const option = document.createElement("option");
          option.value = choice;
          option.textContent = choice;
          input.append(option);
        });
      } else if (definition.kind === "multiline") input.rows = 4;
      else input.type = definition.kind === "boolean" ? "checkbox" : definition.kind === "integer" ? "number" : "text";
      if (definition.kind === "integer") {
        input.min = definition.minimum;
        input.max = definition.maximum;
        input.step = 1;
      }
      input.required = !["boolean", "optional_ipv4_address"].includes(definition.kind);
      input.maxLength = 16384;
      if (definition.pattern) input.pattern = definition.pattern;
      if (definition.kind === "boolean") {
        input.checked = retained[definition.name] ?? definition.default ?? false;
        input.className = "recipe-checkbox";
      } else input.value = retained[definition.name] ?? definition.default ?? "";
      input.autocomplete = "off";
      input.setAttribute("aria-describedby", help.id);
      label.htmlFor = input.id;
      help.textContent =
        definition.description +
        (definition.kind === "optional_ipv4_address"
          ? " Optional; leave blank for cloud allocation."
          : definition.required_when
          ? " Required when this option is enabled."
          : definition.default !== null
          ? " A default is provided; review it for your project."
          : " Required for this recipe.");
      if (definition.kind === "optional_ipv4_address") help.dataset.baseHelp = help.textContent;
      group.append(label, input, help);
    }
    const sectionName = inputSections.find(([, names]) => names.includes(definition.name))?.[0] ?? "Workload inputs";
    if (!sections.has(sectionName)) {
      const section = document.createElement("fieldset");
      section.className = "recipe-input-section";
      const heading = document.createElement("legend");
      heading.textContent = sectionName;
      section.append(heading);
      sections.set(sectionName, section);
    }
    sections.get(sectionName).append(group);
  });
  inputSections.forEach(([name]) => {
    if (sections.has(name)) container.append(sections.get(name));
  });
  contractKey = key;
  updateInputVisibility();
  updatePrivateAddressHint();
}

function updatePrivateAddressHint() {
  const help = byId("recipe-help-private_ip_address");
  if (!help) return;
  const config = configuration();
  const range = vmPrivateAddressRange(config.provider, config.is_public, byId("recipe-network_cidr")?.value);
  help.textContent = help.dataset.baseHelp + (range
    ? ` Usable addresses: ${range.first} through ${range.last} in subnet ${range.subnet}. Availability is not checked.`
    : " Enter a supported network address range to see usable addresses.");
}

function updateInputVisibility() {
  contract.forEach((definition) => {
    if (!definition.visible_when) return;
    const visible = Object.entries(definition.visible_when).every(([name, expected]) => {
      const input = byId(`recipe-${name}`);
      return input && (input.type === "checkbox" ? input.checked : input.value) === expected;
    });
    byId(`recipe-group-${definition.name}`).hidden = !visible;
    const input = byId(`recipe-${definition.name}`);
    if (input) input.disabled = busy || !visible;
  });
}

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  const label =
    theme === "dark" ? "Switch to light theme" : "Switch to dark theme";
  byId("theme-button").textContent = theme === "dark" ? "☀" : "☾";
  byId("theme-button").setAttribute("aria-label", label);
  byId("theme-button").title = label;
  try {
    localStorage.setItem("terraforma-theme", theme);
  } catch {}
}
try {
  setTheme(
    localStorage.getItem("terraforma-theme") === "light" ? "light" : "dark",
  );
} catch {
  setTheme("dark");
}
byId("theme-button").addEventListener("click", () =>
  setTheme(
    document.documentElement.dataset.theme === "dark" ? "light" : "dark",
  ),
);

function configuration() {
  return {
    provider: form.querySelector('input[name="provider"]:checked').value,
    project_name: byId("project-name").value,
    architecture_type: form.querySelector(
      'input[name="architecture_type"]:checked',
    ).value,
    is_public: byId("public-access").checked,
    enable_encryption: byId("encryption").checked,
  };
}

function saveChoices() {
  try {
    if (byId("remember-choice").checked) {
      localStorage.setItem(
        "terraforma-choices",
        JSON.stringify({ version: 1, config: configuration(), step }),
      );
    } else {
      localStorage.removeItem("terraforma-choices");
    }
  } catch {}
}

function restoreChoices() {
  try {
    const saved = JSON.parse(localStorage.getItem("terraforma-choices"));
    const config = saved?.config;
    if (
      saved?.version !== 1 ||
      !config ||
      !["aws", "azure", "gcp"].includes(config.provider) ||
      ![
        "single_web_server",
        "virtual_machine",
        "windows_virtual_machine",
        "load_balanced_tier",
        "secure_database",
        "static_site",
      ].includes(config.architecture_type) ||
      typeof config.project_name !== "string" ||
      !/^[a-z][a-z0-9-]{1,18}[a-z0-9]$/.test(config.project_name) ||
      typeof config.is_public !== "boolean" ||
      typeof config.enable_encryption !== "boolean"
    )
      return;
    form.querySelector(
      `input[name="provider"][value="${config.provider}"]`,
    ).checked = true;
    form.querySelector(
      `input[name="architecture_type"][value="${config.architecture_type}"]`,
    ).checked = true;
    byId("project-name").value = config.project_name;
    byId("public-access").checked = config.is_public;
    byId("encryption").checked = config.enable_encryption;
    byId("remember-choice").checked = true;
    showStep(
      Number.isInteger(saved.step) && saved.step >= 0 && saved.step <= 2
        ? saved.step
        : 0,
    );
    notify(
      "Your saved choices were restored from this browser. Generate again to preview the files.",
    );
  } catch {}
}

function notify(message, error = false) {
  byId("notice").textContent = message;
  byId("notice").classList.toggle("error", error);
  byId("notice").hidden = !message;
}

function setBusy(value) {
  busy = value;
  form.querySelectorAll("input, textarea, select").forEach((input) => {
    input.disabled = value;
  });
  byId("next-button").disabled = value;
  byId("back-button").disabled = value || step === 0;
  byId("validate-button").disabled = value || !project;
  byId("download-button").disabled = value || !project;
  byId("ai-option").disabled = value || !aiAvailable;
  byId("load-project-button").disabled = value;
  byId("review-plan-button").disabled = value;
  byId("target-preflight-consent").disabled = value || !project?.specification;
  byId("target-machine-check").disabled = value || byId("target-machine-option").hidden;
  byId("target-preflight-button").disabled = value || !project?.specification || !byId("target-preflight-consent").checked;
  form.setAttribute("aria-busy", String(value));
  updateInputVisibility();
}

function showStep(index) {
  step = index;
  steps.forEach((element, position) => {
    element.hidden = position !== index;
  });
  document.querySelectorAll(".step").forEach((element, position) => {
    element.classList.toggle("active", position === index);
    element.classList.toggle("complete", position < index);
    if (position === index) element.setAttribute("aria-current", "step");
    else element.removeAttribute("aria-current");
  });
  byId("step-count").textContent = `STEP ${index + 1} OF 3`;
  byId("next-button").textContent =
    index === 2 ? "Generate Terraform →" : "Continue →";
  byId("back-button").disabled = index === 0;
  const legend = steps[index].querySelector("legend");
  legend.tabIndex = -1;
  legend.focus();
  saveChoices();
}

function updateGuidance() {
  const windowsChoice = byId("windows-vm-choice");
  const windowsSupported = ["aws", "azure", "gcp"].includes(form.elements.provider.value);
  windowsChoice.hidden = !windowsSupported;
  windowsChoice.querySelector("input").disabled = !windowsSupported;
  if (!windowsSupported && form.elements.architecture_type.value === "windows_virtual_machine") {
    form.querySelector('[name="architecture_type"][value="virtual_machine"]').checked = true;
  }
  const config = configuration();
  const storageAlwaysEncrypted =
    config.provider === "gcp" ||
    config.architecture_type === "static_site" ||
    (config.provider === "azure" &&
      config.architecture_type === "secure_database");
  byId("encryption-help").textContent = storageAlwaysEncrypted
    ? "This service always encrypts data with provider-managed keys."
    : config.provider === "azure"
      ? "Also enable encryption at host. Requires subscription and VM-size support."
      : "Enable customer-managed KMS encryption for your stored data.";
  const notes = {
    windows_virtual_machine: config.provider === "gcp" ? "RDP is restricted to your administrator network. Set the requested user password separately through Google Cloud after provisioning; TerraForma does not create the account or collect its password. Private VMs need routed access and Windows activation prerequisites." : config.provider === "azure" ? "RDP is restricted to your administrator network. Supply TF_VAR_admin_password externally. AzureRM stores the password in state and saved plans; protect them before use. TerraForma configures no protected backend." : "RDP is restricted to your administrator network. Supply an RSA public key and recover the Administrator password separately through EC2 with its matching private key. Private VMs require a routed access path. No password or private key is collected.",
    virtual_machine: "SSH is restricted to your administrator network. AWS/Azure need your public key; Google uses OS Login IAM access. Private VMs require a routed access path. No application is installed.",
    single_web_server: config.is_public
      ? "Public mode opens HTTP access. SSH stays closed by default. Add TLS before sensitive use."
      : "Your web server is reached through its cloud network. Outbound NAT may incur charges.",
    load_balanced_tier:
      "Your selected number of servers shares traffic through a load balancer. Each server adds compute and disk cost.",
    secure_database: config.is_public
      ? "You must supply a restricted client IP or network before deployment. Database passwords are kept in Terraform variables."
      : "Your database stays on a private cloud network. A standby, backups, and deletion protection are included.",
    static_site: config.is_public
      ? "Anyone can read your website objects. Cloud account or organization policy may restrict public hosting."
      : "Private mode stores website files for authenticated access. It does not create a public website.",
  };
  byId("configuration-note").textContent = notes[config.architecture_type];
}

async function api(path, body, raw = false) {
  if (!token)
    throw new Error(
      "The local connection is not ready. Refresh this page and try again.",
    );
  const response = await fetch(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-TerraForma-Token": token,
    },
    body: raw ? body : JSON.stringify(body),
  });
  if (!response.ok) {
    const text = await response.text();
    let detail = text;
    let field = null;
    try {
      const parsed = JSON.parse(text);
      if (typeof parsed.field === "string") field = parsed.field;
      detail = Array.isArray(parsed.detail)
        ? parsed.detail.map((item) => item.msg).join("; ")
        : parsed.detail || text;
    } catch {
      detail = text || "The local request failed.";
    }
    const error = new Error(detail);
    error.field = field;
    throw error;
  }
  return response;
}

function renderFile(file) {
  selectedFile = file;
  byId("code-preview").textContent = project.files[file];
  document.querySelectorAll(".file-tab").forEach((tab) => {
    const active = tab.dataset.file === file;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", String(active));
    tab.tabIndex = active ? 0 : -1;
    tab.id = `${tab.dataset.file.replace(".tf", "")}-tab`;
    if (active) byId("code-panel").setAttribute("aria-labelledby", tab.id);
  });
}

function renderProject(result) {
  project = result;
  byId("target-preflight-panel").hidden = !result.specification;
  byId("target-preflight-consent").checked = false;
  byId("target-machine-check").checked = false;
  byId("target-machine-option").hidden = !["virtual_machine", "windows_virtual_machine", "single_web_server", "load_balanced_tier"].includes(result.specification?.recipe.architecture_type);
  byId("target-preflight-button").disabled = true;
  byId("target-preflight-results").replaceChildren();
  byId("preview-empty").hidden = true;
  byId("preview-content").hidden = false;
  byId("preview-badge").textContent = "3 FILES READY";
  renderFile("main.tf");
  byId("project-details").hidden = false;
  byId("target-description").hidden = !result.target;
  if (result.target) {
    const targetName = {aws: "AWS account", azure: "Azure subscription", gcp: "Google Cloud project"}[result.target.provider];
    byId("target-description").textContent = `Target ${targetName}: ${result.target.account_reference}. Environment label: ${result.target.environment}. Identity has not been verified offline.`;
  }
  byId("project-notes").replaceChildren(
    ...result.notes.map((text) => {
      const item = document.createElement("li");
      item.textContent = text;
      return item;
    }),
  );
  byId("choice-summary").hidden = !result.choice_summary?.length;
  byId("choice-summary-list").replaceChildren(
    ...(result.choice_summary || []).map((choice) => {
      const row = document.createElement("div");
      const label = document.createElement("dt");
      label.textContent = choice.label;
      const value = document.createElement("dd");
      value.textContent = `${choice.value} (${choice.source})`;
      row.append(label, value);
      return row;
    }),
  );
  const inputs = result.required_inputs.map((input) => {
    const item = document.createElement("div");
    item.className = "input-item";
    const name = document.createElement("code");
    name.textContent = input.name;
    const description = document.createElement("p");
    description.textContent = input.description;
    item.append(name, description);
    return item;
  });
  if (!inputs.length) {
    const message = document.createElement("p");
    message.textContent =
      "No extra required variables. Configure your cloud credentials before planning.";
    inputs.push(message);
  }
  byId("required-inputs").replaceChildren(...inputs);
  byId("resource-guide").hidden = false;
  byId("infrastructure-route").replaceChildren(
    ...result.guide.route.map((name) => {
      const node = document.createElement("li");
      node.textContent = name;
      return node;
    }),
  );
  byId("component-guide").replaceChildren(
    ...result.guide.components.map((component) => {
      const card = document.createElement("article");
      card.className = "component-card";
      const heading = document.createElement("h3");
      heading.textContent = component.name;
      const text = document.createElement("p");
      text.textContent = component.explanation;
      card.append(heading, text);
      return card;
    }),
  );
}

byId("load-project-button").addEventListener("click", () => {
  if (!busy) byId("project-file").click();
});

byId("project-file").addEventListener("change", async () => {
  const file = byId("project-file").files[0];
  if (!file || busy) return;
  setBusy(true);
  try {
    if (file.size > 64 * 1024) throw new Error("Project files must be at most 64 KiB.");
    const result = await (await api("/api/projects/import", await file.text(), true)).json();
    const specification = result.specification;
    const config = specification.recipe;
    form.querySelector(`input[name="provider"][value="${config.provider}"]`).checked = true;
    form.querySelector(`input[name="architecture_type"][value="${config.architecture_type}"]`).checked = true;
    byId("project-name").value = config.project_name;
    byId("public-access").checked = config.is_public;
    byId("encryption").checked = config.enable_encryption;
    byId("remember-choice").checked = false;
    byId("ai-option").checked = false;
    contractKey = "";
    await loadRecipeInputs();
    Object.entries(specification.inputs).forEach(([name, value]) => {
      const input = byId(`recipe-${name}`);
      if (typeof value === "boolean") input.checked = value;
      else input.value = value;
    });
    updateInputVisibility();
    showStep(2);
    updateGuidance();
    byId("validation-panel").hidden = true;
    renderProject(result);
    notify("Project loaded. Review its inputs, generate changes, or export it again. Credentials and secrets remain external.");
  } catch (error) {
    notify(error.message, true);
  } finally {
    byId("project-file").value = "";
    setBusy(false);
  }
});

byId("review-plan-button").addEventListener("click", () => {
  if (!busy) byId("plan-file").click();
});

byId("plan-file").addEventListener("change", async () => {
  const file = byId("plan-file").files[0];
  if (!file || busy) return;
  setBusy(true);
  const results = byId("plan-review-results");
  results.hidden = false;
  results.textContent = "Reviewing the plan locally…";
  try {
    if (file.size > 8 * 1024 * 1024) throw new Error("Plan JSON files must be at most 8 MiB.");
    const report = await (await api("/api/plans/review", await file.arrayBuffer(), true)).json();
    results.replaceChildren(
      diagnostic(
        report.status === "blocked" ? "Changes need attention" : "Manual review required",
        "This report does not approve deployment. " + report.limitations,
      ),
      diagnostic("Planned actions", Object.entries(report.actions).map(([action, count]) => `${action}: ${count}`).join("; ") || "No resource changes listed."),
    );
    report.findings.forEach((finding) => {
      results.append(diagnostic(`${finding.severity === "block" ? "Blocked" : "Review"}: ${finding.code.replaceAll("_", " ")}`, `${finding.resource_id}: ${finding.message}`));
    });
    results.append(diagnostic("Review record", `Policy ${report.policy_version}\nPlan JSON SHA-256: ${report.artifact_sha256}`, true));
    notify("Local plan review complete. Review the findings and gaps before any deployment.");
  } catch (error) {
    results.textContent = error.message;
    notify(error.message, true);
  } finally {
    byId("plan-file").value = "";
    setBusy(false);
  }
});

function diagnostic(title, message, isCode = false) {
  const section = document.createElement("div");
  section.className = "diagnostic";
  const heading = document.createElement("h3");
  heading.textContent = title;
  const content = document.createElement(isCode ? "pre" : "p");
  content.textContent = message;
  section.append(heading, content);
  return section;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (busy) return;
  if (step < 2) {
    if (step === 1) {
      setBusy(true);
      try {
        await loadRecipeInputs();
      } catch (error) {
        notify(error.message, true);
        return;
      } finally {
        setBusy(false);
      }
    }
    showStep(step + 1);
    updateGuidance();
    return;
  }
  if (!byId("project-name").reportValidity()) return;
  const config = configuration();
  setBusy(true);
  notify("Generating your Terraform configuration…");
  try {
    await loadRecipeInputs();
    setBusy(false);
    const invalid = Array.from(
      byId("recipe-inputs").querySelectorAll("input, textarea, select"),
    ).find((input) => !input.checkValidity());
    if (invalid) {
      notify("Complete the required recipe inputs before generating.", true);
      setBusy(false);
      invalid.reportValidity();
      return;
    }
    setBusy(true);
    renderProject(
      await (await api("/api/generate", projectSpecification())).json(),
    );
    notify(
      "Your three files are ready. Review the inputs below, validate locally, or download your project.",
    );
  } catch (error) {
    notify(error.message, true);
    setBusy(false);
    const field = error.field ? byId(`recipe-${error.field}`) : null;
    if (field) {
      field.setCustomValidity(error.message);
      field.setAttribute("aria-invalid", "true");
      field.reportValidity();
    }
  } finally {
    setBusy(false);
  }
});

byId("next-button").formNoValidate = true;
byId("back-button").addEventListener("click", () => {
  if (!busy && step > 0) showStep(step - 1);
});
form.addEventListener("input", (event) => {
  updateInputVisibility();
  updatePrivateAddressHint();
  if (typeof event.target.setCustomValidity === "function") {
    event.target.setCustomValidity("");
    event.target.removeAttribute("aria-invalid");
  }
  updateGuidance();
  saveChoices();
  if (event.target.id === "remember-choice") return;
  if (project) {
    project = null;
    byId("preview-empty").hidden = false;
    byId("preview-content").hidden = true;
    byId("preview-badge").textContent = "PREVIEW";
    byId("project-details").hidden = true;
    byId("resource-guide").hidden = true;
    byId("validation-panel").hidden = true;
    byId("target-preflight-panel").hidden = true;
    byId("target-preflight-consent").checked = false;
    byId("target-machine-check").checked = false;
    byId("target-preflight-button").disabled = true;
    byId("target-preflight-results").replaceChildren();
    notify(
      "Your settings changed. Generate again to preview the updated files.",
    );
  }
});

document.querySelectorAll(".file-tab").forEach((tab, index, tabs) => {
  tab.addEventListener("click", () => {
    if (project) renderFile(tab.dataset.file);
  });
  tab.addEventListener("keydown", (event) => {
    if (
      !project ||
      !["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)
    )
      return;
    event.preventDefault();
    const next =
      event.key === "Home"
        ? 0
        : event.key === "End"
          ? tabs.length - 1
          : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) %
            tabs.length;
    renderFile(tabs[next].dataset.file);
    tabs[next].focus();
  });
});

byId("copy-button").addEventListener("click", async () => {
  if (!project) return;
  try {
    await navigator.clipboard.writeText(project.files[selectedFile]);
    notify(`Copied ${selectedFile}.`);
  } catch {
    notify(
      "Clipboard access is unavailable. Select the code and copy it manually.",
      true,
    );
  }
});

byId("download-button").addEventListener("click", async () => {
  if (busy || !project) return;
  const config = configuration();
  setBusy(true);
  try {
    const response = await api(
      "/api/download",
      project.specification || config,
    );
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = `${config.project_name}.zip`;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
    notify(
      `Your ${config.project_name}.zip download includes all three Terraform files and a project guide.`,
    );
  } catch (error) {
    notify(error.message, true);
  } finally {
    setBusy(false);
  }
});

byId("target-preflight-consent").addEventListener("change", () => setBusy(busy));

byId("target-preflight-button").addEventListener("click", async () => {
  if (busy || !project?.specification || !byId("target-preflight-consent").checked) return;
  const payload = {specification: project.specification, verify_target: true, verify_machine: byId("target-machine-check").checked};
  setBusy(true);
  const content = byId("target-preflight-results");
  content.textContent = "Checking the selected target through your cloud CLI. No infrastructure is being deployed.";
  try {
    const report = await (await api("/api/projects/preflight", payload)).json();
    const titles = {
      target_confirmed: "Cloud target matches",
      target_mismatch: "Different cloud target",
      target_not_ready: "Cloud target needs attention",
      unavailable: "Cloud CLI setup needed",
      failed: "Cloud target check failed",
      invalid_response: "Target response needs review",
      not_checked: "Cloud target not checked",
    };
    content.replaceChildren(
      diagnostic(titles[report.status] || "Cloud target check", report.message, report.status === "target_confirmed"),
      diagnostic("Before planning", "Your cloud CLI can use different credentials from Terraform. Review resource permissions, availability, quotas and connectivity before planning. This check does not approve deployment.", true),
    );
    if (report.machine_check?.status && !["not_checked", "not_applicable"].includes(report.machine_check.status)) {
      const machineMessages = {
        metadata_confirmed: "The selected size passes this recipe's requested CPU, boot, encryption and networking metadata checks. Subscription feature registration, capacity, quotas, guest drivers, image and disk compatibility still need review.",
        architecture_incompatible: "This size reports a CPU architecture that does not support the current x86 image templates. Choose a compatible size before planning.",
        architecture_unknown: "The metadata does not establish CPU architecture. Verify it against the selected x86 image before planning.",
        boot_features_incompatible: "This Azure size reports missing Gen2 or Trusted Launch support needed by the generated VM. Choose a supported size before planning.",
        boot_features_unknown: "The Azure metadata does not establish Gen2 support needed for this VM. Verify Gen2 and Trusted Launch support before planning; CPU compatibility alone is insufficient.",
        network_features_incompatible: "This Azure size reports no accelerated networking support. Disable that option or choose a supported size before planning.",
        network_features_unknown: "The Azure metadata does not establish accelerated networking support. Verify the selected size and guest-driver support before planning.",
        encryption_features_incompatible: "This Azure size reports no encryption-at-host support requested by the recipe. Choose a supported size and verify subscription feature registration before planning.",
        encryption_features_unknown: "The Azure metadata does not establish encryption-at-host support. Verify size support and subscription feature registration before planning.",
        restricted: "The selected size reports restrictions or deprecation. Review those in your cloud tools before planning.",
        not_found: "The selected size was not found in the returned metadata for this region or zone.",
        failed: "The VM-size read failed or exceeded its limits. Check CLI authentication, permissions and the selected size separately.",
        invalid_response: "The VM-size response could not be checked. Review it separately in your cloud tools.",
      };
      content.append(diagnostic("VM size metadata", machineMessages[report.machine_check.status] || "VM metadata needs separate review."));
    }
    const reference = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = "Configuration reference";
    const digest = document.createElement("p");
    digest.textContent = `Questionnaire SHA-256: ${report.specification_sha256}`;
    reference.append(summary, digest);
    content.append(reference);
    notify("Cloud target check complete. Review its result and remaining checks.");
  } catch (error) {
    content.replaceChildren(diagnostic("Target check unavailable", error.message));
    notify(error.message, true);
  } finally {
    byId("target-preflight-consent").checked = false;
    byId("target-machine-check").checked = false;
    setBusy(false);
  }
});

byId("validate-button").addEventListener("click", async () => {
  if (busy || !project) return;
  const payload = {
    config: project.specification || configuration(),
    explain_with_ai: byId("ai-option").checked,
  };
  setBusy(true);
  byId("validation-panel").hidden = false;
  byId("validation-state").textContent = "CHECKING";
  byId("validation-results").textContent =
    "Initializing providers and checking a temporary copy. First-time provider downloads can take a few minutes. Your downloaded files are unchanged.";
  notify("Validation is running locally. No infrastructure is being deployed.");
  try {
    const result = await (await api("/api/validate", payload)).json();
    const content = byId("validation-results");
    content.replaceChildren();
    byId("validation-state").textContent = result.is_valid
      ? "PASSED"
      : "NEEDS ATTENTION";
    if (result.is_valid) {
      content.append(
        diagnostic(
          "Your configuration passed",
          "Terraform validation and TFLint passed. This checks structure and lint rules; cloud permissions, costs, and deployment still need review.",
        ),
      );
    } else {
      result.errors.forEach((error) =>
        content.append(
          diagnostic(
            error.tool === "tflint" ? "TFLint" : "Terraform",
            error.message,
            true,
          ),
        ),
      );
    }
    if (result.suggestion) {
      content.append(
        diagnostic("AI explanation", result.suggestion.friendly_explanation),
      );
      content.append(
        diagnostic(
          "Suggested fix · review before editing",
          result.suggestion.recommended_fix,
          true,
        ),
      );
    }
    if (result.ai_error)
      content.append(diagnostic("AI explanation unavailable", result.ai_error));
    notify(
      result.is_valid
        ? "Local checks passed. You can download your project when you’re ready."
        : "The local checks need attention. Read the results below.",
      !result.is_valid,
    );
  } catch (error) {
    byId("validation-state").textContent = "UNAVAILABLE";
    byId("validation-results").textContent = error.message;
    notify(error.message, true);
  } finally {
    setBusy(false);
  }
});

byId("help-button").addEventListener("click", () =>
  byId("help-dialog").showModal(),
);
byId("help-close").addEventListener("click", () => byId("help-dialog").close());
byId("help-done").addEventListener("click", () => byId("help-dialog").close());
byId("help-tools").addEventListener("click", () => {
  byId("help-dialog").close();
  byId("tools-dialog").showModal();
});
byId("tool-setup-button").addEventListener("click", () =>
  byId("tools-dialog").showModal(),
);
byId("tools-close").addEventListener("click", () =>
  byId("tools-dialog").close(),
);
byId("tools-done").addEventListener("click", () =>
  byId("tools-dialog").close(),
);

async function initialize() {
  restoreChoices();
  updateGuidance();
  try {
    const response = await fetch("/api/session");
    if (!response.ok)
      throw new Error(
        "The local server is unavailable. Restart terraforma serve and refresh this page.",
      );
    const session = await response.json();
    token = session.token;
    if (step === 2) await loadRecipeInputs();
    aiAvailable = session.ai_available;
    byId("version").textContent = `TerraForma-IaC v${session.version}`;
    Object.entries(session.tools).forEach(([name, ready]) => {
      const status = byId(`${name}-status`);
      status.textContent = ready ? "Available ✓" : "Not installed";
      status.classList.toggle("ready", ready);
    });
    byId("tools-help").textContent = Object.values(session.tools).every(Boolean)
      ? "Ready to validate your generated configuration."
      : "Install Terraform and TFLint on PATH to run local checks. Generation and downloads work now.";
    byId("ai-option").disabled = !aiAvailable;
    if (!aiAvailable)
      byId("ai-help").textContent =
        "Set OPENAI_API_KEY before launching to enable. Generation stays local.";
  } catch (error) {
    notify(error.message, true);
  }
}
initialize();
