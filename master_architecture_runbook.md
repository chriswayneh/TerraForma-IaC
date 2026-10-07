# Terraform GuardRails Wizard: Master System Architecture Runbook

This document acts as the complete, unified source of truth for the **Terraform GuardRails Wizard** open-source portfolio project. It consolidates the full system blueprint, dataset schemas, step-by-step wizard rules, sandbox execution pipelines, and AI prompt contracts into a single reference guide.

---

## 1. Directory Tree & Codebase Layout

Instruct your file-generation AI agents to map out the workspace directory using this exact structural path hierarchy:

```text
terraform-guardrails-wizard/
├── .github/workflows/ci.yml       # Automated application testing
├── app/                           # Backend Application Engine (Python/FastAPI)
│   ├── __init__.py
│   ├── main.py                    # FastAPI Endpoint Sandbox Pipeline
│   └── diagnostics.py             # AI Parser Framework Logic
├── src/                           # Frontend React Web Engine (TypeScript/Tailwind)
│   ├── components/
│   │   ├── CodeViewer.tsx         # Monaco Editor Implementation
│   │   ├── DiagnosticsPanel.tsx   # Friendly AI Error Cards
│   │   └── WizardForm.tsx         # Step-by-Step UI Questionnaire
│   ├── config/
│   │   └── wizardQuestions.ts     # Conditional Logic Gate Blueprint
│   ├── App.tsx
│   └── main.tsx
├── Dockerfile                     # Bundles app with Terraform, TFLint & TFsec
├── README.md                      # Comprehensive project documentation
└── requirements.txt
```

---

## 2. Global AI Prompt Strategy (`AI_INSTRUCTIONS.md`)

Save this block as `AI_INSTRUCTIONS.md` at the root of your workspace. Paste this text into any new chat instance to align your sub-agents instantly:

```markdown
# Role & Context Alignment
You are an expert DevOps and Full-Stack AI Engineer. You are helping me build an open-source GitHub portfolio project called "Terraform GuardRails Wizard". 

## Project Objective
A visual web application that lets beginners generate Terraform code via a TurboTax-style multi-step questionnaire, executes background testing/linting binaries locally, intercepts obscure CLI error logs, and uses an AI API to provide friendly, human-readable structural and security changes.

## Global Tech Stack
- Frontend: React (TypeScript, Tailwind CSS, Monaco Editor)
- Backend: FastAPI (Python 3.11+) executing sub-processes locally
- Validation Tools: Native Terraform CLI, TFLint, and TFsec binaries
- Architecture Data Contract: Configured exactly to `project_schema.json` rules

## Development Rules for AI Code Generation
1. Python Sub-processes: When executing `terraform validate` or linting commands, always write files to a temporary, isolated unique directory path per user session to avoid cross-contamination.
2. Error Extraction: Capture both stdout and stderr. Do not return raw bash outputs to the user directly; always prepare the error text payload structurally so it can be passed to an LLM context window.
3. Separation of Concerns: The API backend must remain purely stateless. All persistent states regarding the current phase of the user wizard must stay inside the React frontend hook context.
4. Modular HCL: Generated infrastructure blocks must follow HashiCorp modern practices (separate variables blocks, absolute provider locks, distinct local state blocks).
```

---

## 3. The Interactive Wizard Logic (Frontend Configuration)

This TypeScript file manages the step-by-step form state engine.

```typescript
// path: src/config/wizardQuestions.ts
export interface WizardQuestion {
  id: string;
  step: number;
  title: string;
  description: string;
  type: 'select' | 'boolean' | 'input';
  options?: string[];
  dependsOn?: { questionId: string; value: any };
}

export const WIZARD_STEPS: WizardQuestion[] = [
  {
    id: "provider",
    step: 1,
    title: "Cloud Provider",
    description: "Which cloud infrastructure ecosystem are you deploying to?",
    type: "select",
    options: ["aws", "azure", "gcp"]
  },
  {
    id: "architecture_type",
    step: 2,
    title: "Application Type",
    description: "What type of workload are you provisioning?",
    type: "select",
    options: ["single_web_server", "load_balanced_tier", "secure_database"]
  },
  {
    id: "is_public",
    step: 3,
    title: "Network Exposure",
    description: "Should this workload be accessible directly via the public internet?",
    type: "boolean"
  },
  {
    id: "enable_encryption",
    step: 4,
    title: "Data Security",
    description: "Do you require strict encryption-at-rest using managed KMS keys?",
    type: "boolean"
  }
];
```

---

## 4. The Core Pipeline Sandbox Engine (Backend API)

This production-grade FastAPI runtime sets up ephemeral workspaces, writes generated files, and reads low-level subprocess outputs.

```python
# path: app/main.py
import os
import subprocess
import uuid
import shutil
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Optional

app = FastAPI(title="Terraform GuardRails Engine", version="1.0.0")

class CodePayload(BaseModel):
    main_tf: str
    variables_tf: Optional[str] = ""
    outputs_tf: Optional[str] = ""

class ValidationErrorDetail(BaseModel):
    tool: str
    raw_output: str
    friendly_explanation: Optional[str] = None
    recommended_fix: Optional[str] = None

class ValidationResponse(BaseModel):
    is_valid: bool
    errors: List[ValidationErrorDetail]

@app.post("/api/v1/validate", response_model=ValidationResponse)
async def validate_terraform(payload: CodePayload):
    # Step 1: Establish isolated background compilation sandbox
    sandbox_id = str(uuid.uuid4())
    sandbox_dir = f"/tmp/tf_sandbox_{sandbox_id}"
    os.makedirs(sandbox_dir, exist_ok=True)
    
    try:
        # Step 2: Write ephemeral code files locally
        with open(os.path.join(sandbox_dir, "main.tf"), "w") as f:
            f.write(payload.main_tf)
        with open(os.path.join(sandbox_dir, "variables.tf"), "w") as f:
            f.write(payload.variables_tf)
        with open(os.path.join(sandbox_dir, "outputs.tf"), "w") as f:
            f.write(payload.outputs_tf)
            
        # Initialize working workspace context
        subprocess.run(["terraform", "init", "-backend=false"], cwd=sandbox_dir, capture_output=True, text=True)
        
        # Step 3: Execute low-level structural code analysis
        result = subprocess.run(["terraform", "validate", "-json"], cwd=sandbox_dir, capture_output=True, text=True)
        
        errors_list = []
        is_valid = (result.returncode == 0)
        
        if not is_valid:
            errors_list.append(ValidationErrorDetail(
                tool="terraform_validate",
                raw_output=result.stdout if result.stdout else result.stderr
            ))
            
        return ValidationResponse(is_valid=is_valid, errors=errors_list)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sandbox Execution Failure: {str(e)}")
        
    finally:
        # Step 4: Strict cleanup pass to prevent local disk bloat
        if os.path.exists(sandbox_dir):
            shutil.rmtree(sandbox_dir)
```

---

## 5. The AI Diagnostics Prompt Schema

This utility function captures raw terminal data and converts it into a structured prompt contract for LLM parsers.

```python
# path: app/diagnostics.py
def generate_diagnostics_prompt(raw_error_log: str, source_code: str) -> dict:
    """
    Builds the exact contextual prompt contract payload to feed your AI parser.
    """
    system_role = (
        "You are a compassionate DevOps Mentor specializing in helping junior engineers. "
        "Your job is to analyze cryptic Terraform CLI logs and explain the exact issue "
        "without using complex jargon, then supply the exact fixed code block."
    )
    
    user_prompt = f"""
    The user is trying to deploy infrastructure but their build failed.
    
    [RAW CLI ERROR LOG]
    {raw_error_log}
    
    [ORIGINAL SOURCE CODE DEPLOYED]
    {source_code}
    
    Respond strictly in JSON matching this contract structure:
    {{
      "friendly_explanation": "A clear description of what went wrong conceptually.",
      "recommended_fix": "The exact modified code snippet that completely replaces the broken code block."
    }}
    """
    
    return {
        "system": system_role,
        "messages": [{"role": "user", "content": user_prompt}]
    }
```
