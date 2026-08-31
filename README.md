# PII Redaction Demo

> ## This is a proof of concept. It is not production code.
>
> The **only** purpose of this repository is to demonstrate the **end-to-end flow** of PII
> redaction across Azure AI services — image in, OCR, PII detection, masked output — and to make
> every intermediate step visible so you can see what each service contributes.
>
> **There is no error handling.** No retries, no input validation, no fault isolation, no
> telemetry. Failures surface as raw unhandled exceptions, deliberately, so the cause is obvious
> during a walkthrough.
>
> **Do not run this against real customer data.** Read [Limitations](#limitations) first.
>
> ---
>
> **Personal project disclaimer.** This is independent personal work by Vinod Patil, created
> outside the scope of any employment. It is **not a Microsoft product** and is not affiliated
> with, endorsed by, sponsored by, or supported by Microsoft Corporation. All design choices and
> opinions here are the author's own and do not represent those of any employer. The code is
> provided as-is under the [MIT License](LICENSE), with no warranty and no support commitment.

---

## What it demonstrates

Two channels, one shared Azure AI Services account:

```mermaid
flowchart LR
    subgraph images ["Image channel"]
        A[input-images/*.jpg] --> B[Azure AI Vision<br/>Read / OCR]
        B --> C[Flatten to one document<br/>+ record word boxes]
        C --> D[Azure AI Language<br/>PII detection]
        D --> E[Map entity offsets<br/>back to word boxes]
        E --> F[Pillow draws<br/>black boxes]
        F --> G[output-images/*.jpg]
    end
    subgraph emails ["Email channel"]
        H[input-emails/*.txt] --> I[Azure AI Language<br/>PII detection]
        I --> J[output-emails/*.txt]
    end
```

The interesting part is the image channel. Azure AI Language returns character offsets into a text
document; an image has no character offsets. The pipeline flattens OCR output into a single
document while recording where each recognized word landed, then maps the detected entity spans
back onto the original word polygons so the right pixels get masked.

Emails skip OCR entirely and go straight to PII detection.

---

## Quick start

### Prerequisites

- Python 3.11 or later
- Azure CLI, signed in (`az login`)
- Terraform 1.7 or later
- An Azure subscription where you can create resource groups **and role assignments**

### 1. Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

### 2. Deploy the Azure resources

```powershell
cd infra/terraform/environments/dev
Copy-Item terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars and set subscription_id to your own subscription.
terraform init
terraform plan -out=tfplan
terraform apply tfplan
```

This creates one multi-service Azure AI Services account that serves both Vision and Language,
plus a Foundry project. See [Infrastructure](#infrastructure) for what is provisioned and why.

> Role assignments on the Cognitive Services data plane can take up to ~15 minutes to propagate.
> A `401 PermissionDenied` immediately after `apply` is expected — wait and retry before
> investigating.

### 3. Configure the app

```powershell
cd ../../../..
Copy-Item .env.example .env
terraform -chdir=infra/terraform/environments/dev output -raw ai_services_endpoint
```

Put that endpoint into `.env` as `APP_AI_SERVICES_ENDPOINT`. It is the only required setting.

### 4. Run it

```powershell
# Both channels, with the step-by-step trace report
python -m pii_redaction_demo.main --mode all --trace

# One channel at a time
python -m pii_redaction_demo.main --mode images
python -m pii_redaction_demo.main --mode emails
```

Sample inputs ship in `input-images/` and `input-emails/`. Redacted copies are written to
`output-images/` and `output-emails/` under the original file names.

```text
INFO    pii_redaction_demo.services.pipeline: redacting 5 image(s) from ...\input-images
INFO    pii_redaction_demo.services.pipeline: chat-01-fraud-dispute.jpg: 84 word(s) read, 6 entity(ies), 9 box(es) -> ...
INFO    pii_redaction_demo.main: done: 5 image(s), 5 email(s), 41 PII entity(ies) masked
```

### 5. Open the trace report

`--trace` is the part worth demoing. It writes `data/processed/<timestamp>/` containing the raw
output of every step — source, OCR JSON with word boxes, the flattened document, the detected
entities, and the masked result — plus a `report.html` showing them side by side with the OCR and
PII boxes drawn on the image. Open that file to walk through what each service contributed.

> **The trace directory is an unredacted plaintext PII store.** It holds original text, detected
> entity values, and source images by design, so a reviewer can validate the pipeline. It is
> gitignored. Delete it when you are done.

---

## Command line reference

| Flag | Purpose |
| --- | --- |
| `--mode {images,emails,all}` | Which channel to process. Default `all`. |
| `--trace` | Write per-step artifacts and a side-by-side `report.html`. |
| `--trace-dir` | Where the trace run lands. Default `data/processed`. |
| `--verbose` | Log at `DEBUG` instead of `APP_LOG_LEVEL`. |
| `--input-dir` / `--output-dir` | Override the image directories. |
| `--email-input-dir` / `--email-output-dir` | Override the email directories. |

## Configuration

Settings are read from `.env` with the `APP_` prefix. See `.env.example`.

| Setting | Default | Purpose |
| --- | --- | --- |
| `APP_AI_SERVICES_ENDPOINT` | *(required)* | Shared Vision + Language endpoint |
| `APP_PII_LANGUAGE` | `en` | Language hint passed to Azure AI Language |
| `APP_PII_MIN_CONFIDENCE` | `0.0` | Drop detections below this confidence before masking |
| `APP_LOG_LEVEL` | `INFO` | Root log level |
| `APP_INPUT_IMAGES_DIR` / `APP_OUTPUT_IMAGES_DIR` | `input-images` / `output-images` | Image directories |
| `APP_INPUT_EMAILS_DIR` / `APP_OUTPUT_EMAILS_DIR` | `input-emails` / `output-emails` | Email directories |
| `APP_TRACE_DIR` | `data/processed` | Trace output root |

`APP_PII_MIN_CONFIDENCE=0.0` masks everything Azure AI Language returns, which is the safest
default. Raise it to around `0.8` to see the effect of trading recall for precision.

Authentication uses `DefaultAzureCredential` — no keys anywhere. `az login` is enough locally.

---

## Sample data

> **All sample data in this repository is synthetic. It describes no real person, account, card,
> or organization.**

The emails in `input-emails/` and the chat screenshots in `input-images/` were fabricated for this
demo. They use reserved test ranges wherever one exists:

| Field | Convention |
| --- | --- |
| Names | Locale placeholder names (John Q. Public, Jane A. Bloggs, Taro Yamada, Fulan Al-Fulani) |
| SSNs | The SSA advertising-reserved block `987-65-432x` |
| Addresses | `Example`-named streets |
| Phone numbers | Reserved `555-01xx` and `+44 7700 900xxx` ranges |
| Card numbers | Standard issuer test PANs |
| Email domains | `.test` and `example-*` domains |
| Organizations | Invented brands (Bluecrest Card Services, Fictional Logistics FZE) |

> **Known gap:** the JPEGs in `input-images/` are raster files, so a few pre-existing synthetic
> values are baked into the pixels and were not updated to the ranges above. Notably
> `chat-05-hardship-name-change.jpg` contains a Luhn-valid card number and a valid-format SSN.
> Both are fabricated, but automated DLP scanners may flag them. Regenerate the images if that
> matters in your environment.

---

## Limitations

These are deliberate simplifications, not oversights. Every one must be addressed before this
approach goes near real data.

### 1. There is no error handling

The single largest gap. Failures propagate as unhandled exceptions and the process dies. Missing
entirely:

- **Retries.** No backoff for throttling (HTTP 429) or transient 5xx errors. The Azure SDK
  defaults are not tuned for batch workloads.
- **Input validation.** Unsupported formats, empty or corrupt files, oversized images, and
  unreadable encodings all fail late and unhelpfully.
- **Exit codes and run summaries.** Nothing can orchestrate or monitor this process.
- **Client lifecycle management.** The Azure clients expose `close()` and nothing calls it.
- **Structured logging and telemetry.** The app prints to stdout and never uses the configured
  log level. Correlation IDs per item do not exist.

### 2. Document size limits are not enforced

Azure AI Language caps a single document at ~5,120 characters and a request at ~125,000
characters. `PiiRedactionService` batches by document *count* only (5 per request), so a long
email or a text-heavy image is rejected by the service. Production code must split documents into
service-safe chunks and reassemble the results, remapping entity offsets back to the original.

### 3. There is no per-item fault isolation

Each pipeline processes a directory as a single batch. One bad input aborts the entire run and no
results are written at all. Production code should isolate each file, record failures alongside
successes, and return a per-item status.

### 4. Trace output contains unredacted PII

`--trace` writes original text, detected entity values, source images, and an HTML report into
`data/processed/`. This is intentional so a reviewer can validate the pipeline, but it is a
plaintext PII store. Production code should default to redacted-only artifacts; any full-fidelity
mode needs encryption at rest, access control, retention limits, and audit logging.

### 5. A detection miss is a data leak, not a degraded result

The pipeline treats whatever Azure AI Language returns as complete. It is not. There is no
confidence floor by default, no deterministic backstop, and no quarantine path. Production needs a
defined failure policy — decide up front whether a partially-processed item is withheld rather
than published — plus defense in depth such as regex checks for card numbers alongside the model
output.

### 6. Infrastructure is demo-grade

Terraform state is local, not remote. There is no private networking, no customer-managed keys, no
diagnostic settings, and no lifecycle policy. `dev` is the only environment.

---

## Infrastructure

The `dev` environment provisions a resource group containing a single multi-service Azure AI
Services account, configured as a Foundry resource with one project:

| Resource | Kind | Purpose |
| --- | --- | --- |
| `cog-<prefix>-aiservices-<suffix>` | `AIServices` | Vision Read/OCR **and** Language PII detection |
| `<account>/<project>` | `AIServices` project | Foundry portal playgrounds, evaluations, traces |

`project_management_enabled = true` is what turns the account into a Foundry resource: it makes
the account visible in the Foundry portal and lets it parent `accounts/projects` children. The
flag provisions nothing on its own, so the project is declared explicitly.

The two scopes expose different endpoints:

| Endpoint | Terraform output | Serves |
| --- | --- | --- |
| `https://<account>.cognitiveservices.azure.com/` | `ai_services_endpoint` | Language PII, Vision OCR, Speech, Translator — **what this app calls** |
| `https://<account>.services.ai.azure.com/api/projects/<project>` | `ai_project_endpoint` | Agents, evaluations, datasets, files |

Language and Vision are account-scoped, so the app only needs `APP_AI_SERVICES_ENDPOINT`.

> Language and Vision do not support project-level RBAC isolation, so data-plane role assignments
> must stay at the account scope. Use a separate account, not a separate project, when you need to
> isolate access to redaction itself.

See [docs/architecture.md](docs/architecture.md) for the overall flow.

### Authentication

The account is deployed with `local_auth_enabled = false`, so no API keys are issued and every
call uses an Entra ID token. 

**Data-plane access needs an explicit role.** Subscription Owner or Contributor does **not** grant
it. Grant additional callers via `data_plane_principal_ids`, and set `data_plane_principal_type` to
`ServicePrincipal` for managed identities or app registrations:

```hcl
data_plane_principal_ids  = ["00000000-0000-0000-0000-000000000000"]
data_plane_principal_type = "ServicePrincipal"
```

### Verify

`smoke-test.ps1` reads the endpoint from Terraform outputs, calls both data planes with an Entra
ID token, and confirms the Foundry project exists:

```powershell
./smoke-test.ps1
```

```text
LANGUAGE PII: OK
  redacted: ********'s card number is ******************* and her email is ********************.
  entities: Person, CreditCardNumber, Email
VISION OCR: OK
  lines read: 16
FOUNDRY PROJECT: OK
  <project> (default: True)
```

> Unsupported Image Analysis API versions return `401 PermissionDenied` rather than a version
> error, so a 401 from Vision is not necessarily a permissions problem. This code targets
> `api-version=2023-10-01`.

### Tear down

```powershell
terraform destroy
```

Cognitive Services accounts are soft-deleted. The provider sets
`purge_soft_delete_on_destroy = true` so the name is released; otherwise redeploying with the same
name fails until the soft-deleted account is purged.

---

## Repository layout

```text
src/pii_redaction_demo/
  core/              Configuration (pydantic-settings)
  domain/            Business entities
  providers/         Azure and imaging adapters, plus the protocols they implement
  services/          Pipelines and trace reporting
tests/unit/          Fast, isolated tests
tests/integration/   Boundary and adapter tests (empty)
tests/e2e/           Deployed-system tests (empty)
infra/terraform/     Reusable modules and environment roots
input-emails/        Synthetic sample emails
input-images/        Synthetic sample chat screenshots
data/processed/      Local-only trace output (gitignored)
docs/                Architecture and Foundry reference notes
```

Adapters sit behind protocols in `providers/protocols.py`, so the Azure clients can be swapped for
fakes in tests without touching pipeline logic.

## Development

```powershell
pytest --cov
ruff check .
ruff format --check .
mypy
```

CI runs the same four commands on every push and pull request.

Never commit secrets, customer data, credentials, or Terraform state. The `.gitignore` files
exclude `.env`, `*.tfstate*`, `*.tfvars`, `tfplan`, trace output, and local caches — check
`git status` before your first commit.

## License

MIT. See [LICENSE](LICENSE).
