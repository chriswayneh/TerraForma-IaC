# AI Orchestration Blueprint & Engineering Runbook
**Project:** Terraform GuardRails Wizard (GitHub Portfolio)

This document provides a single machine-readable specification and universal alignment prompt to orchestrate multiple cooperative AI developer agents (ChatGPT, Claude, GitHub Copilot, Cursor) working seamlessly across frontend and backend boundaries.

---

## 1. Global Architecture Blueprint (JSON Schema)
Save this configuration file as `project_schema.json`. It maps the absolute data contracts between the visual multi-step questionnaire frontend and the local sandboxed analysis runtime backend.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "TerraformWizardState",
  "type": "object",
  "properties": {
    "project_metadata": {
      "type": "object",
      "properties": {
        "provider": { "type": "string", "enum": ["aws", "azure", "gcp"] },
        "project_name": { "type": "string" }
      },
      "required": ["provider", "project_name"]
    },
    "wizard_responses": {
      "type": "object",
      "properties": {
        "architecture_type": { "type": "string", "enum": ["web_server", "static_site", "database_cluster"] },
        "is_public": { "type": "boolean" },
        "enable_encryption": { "type": "boolean" }
      },
      "required": ["architecture_type", "is_public", "enable_encryption"]
    },
    "generated_code": {
      "type": "object",
      "properties": {
        "main_tf": { "type": "string" },
        "variables_tf": { "type": "string" },
        "outputs_tf": { "type": "string" }
      }
    },
    "validation_results": {
      "type": "object",
      "properties": {
        "is_valid": { "type": "boolean" },
        "errors": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "tool": { "type": "string", "enum": ["terraform_validate", "tflint", "tfsec"] },
              "raw_output": { "type": "string" },
              "friendly_explanation": { "type": "string" },
              "recommended_fix": { "type": "string" }
            }
          }
        }
      }
    }
  },
  "required": ["project_metadata", "wizard_responses"]
}
```

---

## 2. Universal Context Prompt
Save this block as `AI_INSTRUCTIONS.md`. Inject this markdown payload at the start of any new AI context window or chat configuration script to avoid incompatible architectures:

```markdown
# Role & Context Alignment
You are an expert DevOps and Full-Stack AI Engineer assisting with the "Terraform GuardRails Wizard".

## Project Objective
A visual web application allowing beginners to build valid Terraform code through a step-by-step form wizard, executing background validation sandboxes locally, catching complex CLI error strings, and interpreting them into user-friendly recommendations via an AI engine.

## Global Tech Stack
- Frontend: React (TypeScript, Tailwind CSS, Monaco Editor)
- Backend: FastAPI (Python 3.11+) executing background local sub-processes
- Validation Tools: Native Terraform CLI, TFLint, and TFsec binaries
- Architecture Data Contract: Bound strictly to rules in `project_schema.json`

## Development Constraints
1. Python Sub-processes: Isolate user sessions inside unique filesystem temporary directories to prevent workspace overlapping.
2. Error Extraction: Capture stdout/stderr streams comprehensively. Structure logs into clear payloads before prompting downstream LLMs.
3. Separation of Concerns: The API tier is purely stateless. Maintain all active visual stepper sequences entirely within frontend react contexts.
```
