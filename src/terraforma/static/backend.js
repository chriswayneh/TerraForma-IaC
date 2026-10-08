"use strict";

(() => {
  const dialog = byId("backend-dialog");
  const backendForm = byId("backend-form");
  let definitions = [];
  let checkedPayload = null;
  let pending = false;
  let version = 0;

  function setPending(value) {
    pending = value;
    backendForm.querySelectorAll("input, select").forEach((input) => { input.disabled = value; });
    byId("backend-check").disabled = value || !definitions.length;
    byId("backend-download").disabled = value || !checkedPayload;
    byId("backend-import").disabled = value;
    backendForm.setAttribute("aria-busy", String(value));
  }

  function invalidate() {
    checkedPayload = null;
    for (const definition of definitions) {
      const input = byId(`backend-${definition.name}`);
      if (input) input.removeAttribute("aria-invalid");
      const message = byId(`backend-${definition.name}-error`);
      if (message) {
        message.textContent = "";
        message.hidden = true;
      }
    }
    byId("backend-download").disabled = true;
    byId("backend-results").replaceChildren();
    byId("backend-results").hidden = true;
    byId("backend-status").textContent = "Check inputs before downloading. Cloud verification remains separate.";
  }

  function payload() {
    const data = { schema_version: 1, backend: byId("backend-type").value };
    for (const definition of definitions) {
      const input = byId(`backend-${definition.name}`);
      data[definition.name] = definition.kind === "boolean" ? input.checked : input.value;
    }
    return JSON.stringify(data);
  }

  function renderFields(inputs, values = {}) {
    definitions = inputs;
    byId("backend-fields").replaceChildren();
    for (const definition of definitions) {
      const label = document.createElement("label");
      const input = document.createElement("input");
      input.id = `backend-${definition.name}`;
      input.name = definition.name;
      input.type = definition.kind === "boolean" ? "checkbox" : "text";
      input.required = true;
      input.autocomplete = "off";
      input.spellcheck = false;
      label.className = "input-label";
      label.htmlFor = input.id;
      const hint = document.createElement("p");
      hint.id = `${input.id}-hint`;
      hint.className = "input-help";
      hint.textContent = definition.hint;
      const message = document.createElement("p");
      message.id = `${input.id}-error`;
      message.className = "input-help";
      message.hidden = true;
      input.setAttribute("aria-describedby", `${hint.id} ${message.id}`);
      const value = values[definition.name] ?? definition.default;
      if (definition.kind === "boolean") {
        input.checked = value;
        label.append(input, document.createTextNode(definition.label));
        byId("backend-fields").append(label);
      } else {
        input.className = "text-input";
        input.value = value;
        input.maxLength = 512;
        label.textContent = definition.label;
        byId("backend-fields").append(label, input);
      }
      byId("backend-fields").append(hint, message);
    }
  }

  async function loadFields() {
    const current = ++version;
    definitions = [];
    invalidate();
    byId("backend-fields").replaceChildren();
    byId("backend-status").textContent = "Loading storage questions…";
    setPending(true);
    try {
      const result = await (await api("/api/backends/input-contract", { backend: byId("backend-type").value })).json();
      if (current !== version || !dialog.open) return;
      renderFields(result.inputs);
      invalidate();
    } catch (error) {
      if (current === version) byId("backend-status").textContent = error.message;
    } finally {
      if (current === version) setPending(false);
    }
  }

  byId("backend-open").addEventListener("click", () => {
    if (busy) return;
    dialog.showModal();
    loadFields();
  });
  byId("backend-close").addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => {
    version++;
    definitions = [];
    checkedPayload = null;
    backendForm.reset();
    byId("backend-fields").replaceChildren();
    byId("backend-results").replaceChildren();
    byId("backend-status").textContent = "";
    setPending(false);
  });
  byId("backend-type").addEventListener("change", loadFields);
  byId("backend-fields").addEventListener("input", invalidate);

  byId("backend-import").addEventListener("click", () => {
    if (!pending) byId("backend-file").click();
  });
  byId("backend-file").addEventListener("change", async () => {
    const file = byId("backend-file").files[0];
    if (!file) return;
    byId("backend-file").value = "";
    if (pending || !dialog.open) return;
    const current = ++version;
    invalidate();
    if (file.size > 16 * 1024) {
      byId("backend-status").textContent = "Choose a non-secret backend input file up to 16 KiB. Existing entries were kept.";
      return;
    }
    setPending(true);
    byId("backend-status").textContent = "Checking the saved input file locally…";
    try {
      const raw = await file.arrayBuffer();
      if (current !== version || !dialog.open) return;
      const result = await (await api("/api/backends/import", raw, true)).json();
      if (current !== version || !dialog.open) return;
      byId("backend-type").value = result.intent.backend;
      renderFields(result.inputs, result.intent);
      invalidate();
      byId("backend-status").textContent = "Saved inputs loaded. Review the references and check inputs before downloading. No backend was configured or cloud access verified.";
    } catch (error) {
      if (current === version) byId("backend-status").textContent = error.message + " Existing entries were kept.";
    } finally {
      if (current === version) setPending(false);
    }
  });

  backendForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (pending || !definitions.length || !backendForm.reportValidity()) return;
    const current = version;
    const raw = payload();
    invalidate();
    setPending(true);
    byId("backend-status").textContent = "Checking inputs locally…";
    try {
      const report = await (await api("/api/backends/check", raw, true)).json();
      if (current !== version || !dialog.open) return;
      checkedPayload = raw;
      byId("backend-status").textContent = "Inputs valid. Storage access, locking and recovery still require verification. No backend was configured or deployment approved.";
      const list = document.createElement("ul");
      for (const review of report.required_reviews) {
        const item = document.createElement("li");
        item.textContent = review;
        list.append(item);
      }
      byId("backend-results").replaceChildren(list);
      byId("backend-results").hidden = false;
    } catch (error) {
      if (current === version && dialog.open) {
        byId("backend-status").textContent = error.message;
        if (definitions.some((definition) => definition.name === error.field)) {
          const input = byId(`backend-${error.field}`);
          input.setAttribute("aria-invalid", "true");
          byId(`${input.id}-error`).textContent = error.message;
          byId(`${input.id}-error`).hidden = false;
        }
      }
    } finally {
      if (current === version) {
        setPending(false);
        if (dialog.open) byId("backend-fields").querySelector('[aria-invalid="true"]')?.focus();
      }
    }
  });

  byId("backend-download").addEventListener("click", async () => {
    if (pending || !checkedPayload || checkedPayload !== payload()) return;
    const current = version;
    setPending(true);
    try {
      const response = await api("/api/backends/download", checkedPayload, true);
      const blob = await response.blob();
      if (current !== version || !dialog.open) return;
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "terraforma.backend.json";
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
      byId("backend-status").textContent = "Input file downloaded. This file is separate from your Terraform project; storage has not been configured.";
    } catch (error) {
      if (current === version) byId("backend-status").textContent = error.message;
    } finally {
      if (current === version) setPending(false);
    }
  });
})();
