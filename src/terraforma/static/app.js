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
  const values = new FormData(form);
  return {
    provider: values.get("provider"),
    project_name: values.get("project_name"),
    architecture_type: values.get("architecture_type"),
    is_public: byId("public-access").checked,
    enable_encryption: byId("encryption").checked,
  };
}

function notify(message, error = false) {
  byId("notice").textContent = message;
  byId("notice").classList.toggle("error", error);
  byId("notice").hidden = !message;
}

function setBusy(value) {
  busy = value;
  form.querySelectorAll("input").forEach((input) => {
    input.disabled = value;
  });
  byId("next-button").disabled = value;
  byId("back-button").disabled = value || step === 0;
  byId("validate-button").disabled = value || !project;
  byId("download-button").disabled = value || !project;
  byId("ai-option").disabled = value || !aiAvailable;
  form.setAttribute("aria-busy", String(value));
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
}

function updateGuidance() {
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
    single_web_server: config.is_public
      ? "Public mode opens HTTP access. SSH stays closed by default. Add TLS before sensitive use."
      : "Your web server is reached through its cloud network. Outbound NAT may incur charges.",
    load_balanced_tier:
      "Two servers share traffic through a load balancer. This costs more than a single-server setup.",
    secure_database: config.is_public
      ? "You must supply a restricted client IP or network before deployment. Database passwords are kept in Terraform variables."
      : "Your database stays on a private cloud network. A standby, backups, and deletion protection are included.",
    static_site: config.is_public
      ? "Anyone can read your website objects. Cloud account or organization policy may restrict public hosting."
      : "Private mode stores website files for authenticated access. It does not create a public website.",
  };
  byId("configuration-note").textContent = notes[config.architecture_type];
}

async function api(path, body) {
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
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const text = await response.text();
    let detail = text;
    try {
      const parsed = JSON.parse(text);
      detail = Array.isArray(parsed.detail)
        ? parsed.detail.map((item) => item.msg).join("; ")
        : parsed.detail || text;
    } catch {
      detail = text || "The local request failed.";
    }
    throw new Error(detail);
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
  byId("preview-empty").hidden = true;
  byId("preview-content").hidden = false;
  byId("preview-badge").textContent = "3 FILES READY";
  renderFile("main.tf");
  byId("project-details").hidden = false;
  byId("project-notes").replaceChildren(
    ...result.notes.map((text) => {
      const item = document.createElement("li");
      item.textContent = text;
      return item;
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
    showStep(step + 1);
    updateGuidance();
    return;
  }
  if (!byId("project-name").reportValidity()) return;
  const config = configuration();
  setBusy(true);
  notify("Generating your Terraform configuration…");
  try {
    renderProject(await (await api("/api/generate", config)).json());
    notify(
      "Your three files are ready. Review the inputs below, validate locally, or download your project.",
    );
  } catch (error) {
    notify(error.message, true);
  } finally {
    setBusy(false);
  }
});

byId("next-button").formNoValidate = true;
byId("back-button").addEventListener("click", () => {
  if (!busy && step > 0) showStep(step - 1);
});
form.addEventListener("input", () => {
  updateGuidance();
  if (project) {
    project = null;
    byId("preview-empty").hidden = false;
    byId("preview-content").hidden = true;
    byId("preview-badge").textContent = "PREVIEW";
    byId("project-details").hidden = true;
    byId("resource-guide").hidden = true;
    byId("validation-panel").hidden = true;
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
    const response = await api("/api/download", config);
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

byId("validate-button").addEventListener("click", async () => {
  if (busy || !project) return;
  const payload = {
    config: configuration(),
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
  updateGuidance();
  try {
    const response = await fetch("/api/session");
    if (!response.ok)
      throw new Error(
        "The local server is unavailable. Restart terraforma serve and refresh this page.",
      );
    const session = await response.json();
    token = session.token;
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
