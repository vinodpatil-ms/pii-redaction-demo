# Architecture

## What this does

Two input channels — chat/screenshot images and plain-text emails — are reduced to text, scanned
for PII by Azure AI Language, and masked. Images are masked visually (opaque boxes over the
pixels where the PII was read); emails are masked in the text itself.

```mermaid
flowchart LR
    subgraph inputs [Inputs]
        IMG[/"input-images/<br/>jpg, png, bmp, tiff"/]
        EML[/"input-emails/<br/>txt, eml"/]
    end

    subgraph azure ["Azure AI Services - one account, one endpoint"]
        VISION["Vision Read / OCR<br/>text + word polygons"]
        LANG["Language PII<br/>entities + offsets"]
    end

    subgraph app [pii-redaction-demo]
        FLATTEN["Flatten to one document<br/>keep word-to-offset map"]
        THRESH["Confidence filter<br/>APP_PII_MIN_CONFIDENCE"]
        MAP["Map entity offsets<br/>back to word polygons"]
        MASK["Pillow<br/>draw opaque boxes"]
    end

    subgraph outputs [Outputs]
        OIMG[/"output-images/<br/>masked image"/]
        OEML[/"output-emails/<br/>masked text"/]
        TRACE[/"data/processed/run/<br/>per-step artifacts + report.html"/]
    end

    IMG --> VISION --> FLATTEN --> LANG
    EML --> LANG
    LANG --> THRESH
    THRESH --> MAP --> MASK --> OIMG
    THRESH --> OEML
    MASK -.->|--trace| TRACE
    THRESH -.->|--trace| TRACE

    classDef svc fill:#0b6bcb,stroke:#0b6bcb,color:#fff;
    class VISION,LANG svc;
```

The image path is the interesting one. Azure AI Language works on text and returns character
offsets, but masking an image needs pixel coordinates. The pipeline bridges the two by recording
where every OCR word landed in the flattened document, then translating each PII entity's offset
range back to the polygons of the words it overlaps.

```mermaid
sequenceDiagram
    participant CLI as main.py
    participant P as ImageRedactionPipeline
    participant V as Azure AI Vision
    participant L as Azure AI Language
    participant I as PillowImageRedactor

    CLI->>P: run(input_dir, output_dir)
    loop each image
        P->>V: read_image(bytes)
        V-->>P: lines + words + polygons
        P->>P: _flatten() to document + WordSpan[]
        P->>L: recognize_pii_entities(document)
        L-->>P: entities (offset, length, score)
        P->>P: drop entities below min_confidence
        P->>P: _polygons_for_entities() to overlapping word boxes
        P->>I: mask(bytes, polygons)
        I-->>P: masked image
    end
    P-->>CLI: RedactedImage[]
```

## Code layout

Dependencies point inward. `services/` depends only on the protocols in
`providers/protocols.py`; the Azure and Pillow adapters implement them structurally and are wired
together in `main.py`. Domain objects stay free of SDK types, so the pipelines are testable with
plain stubs and no mocking framework.

```mermaid
flowchart TD
    MAIN["main.py<br/>composition root, CLI, logging"]
    PIPE["services/pipeline.py<br/>ImageRedactionPipeline<br/>EmailRedactionPipeline"]
    PII["services/pii_redaction.py<br/>batching, confidence threshold"]
    TRACE["services/trace_report.py<br/>--trace artifacts + HTML"]
    PROTO["providers/protocols.py<br/>OcrProvider, PiiRedactionProvider<br/>ImageRedactor, ImageAnnotator"]
    AV["providers/azure_vision.py"]
    AL["providers/azure_language.py"]
    PIL["providers/pillow_image.py"]
    DOM["domain/models.py<br/>OcrResult, PiiEntity, RedactionResult"]

    MAIN --> PIPE
    MAIN --> TRACE
    MAIN -.->|constructs| AV
    MAIN -.->|constructs| AL
    MAIN -.->|constructs| PIL
    PIPE --> PII
    PIPE --> PROTO
    PII --> PROTO
    TRACE --> PROTO
    AV -.->|implements| PROTO
    AL -.->|implements| PROTO
    PIL -.->|implements| PROTO
    PIPE --> DOM
    PROTO --> DOM
```

## Authentication

Both data planes sit behind one Azure AI Services account with `local_auth_enabled = false`, so
API keys do not exist. `main.py` creates a single `DefaultAzureCredential` and passes it to both
adapters, which keeps token acquisition and caching in one place. Callers need an explicit
`Cognitive Services User` role assignment on the account — subscription Owner or Contributor does
not grant data-plane access.

## Conventions

Model-specific clients belong in `providers/`; do not call an Azure SDK from `services/` or
`domain/`. Keep evaluation datasets free of sensitive customer data and add automated quality
gates beside conventional tests.

Infrastructure is organized as reusable Terraform modules plus isolated environment roots.
Remote state, provider configuration, resource naming, and policy controls should be selected
when the deployment cloud and environments are known.

See the "Scope: this is a POC" section of the README for the gaps that must be closed before this
design is used against real data.
