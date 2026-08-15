# 🖼️ Diagram Gallery

All diagrams are stored as **PNG** wiki attachments (rendered at 2x for crisp zooming) under
`/.attachments/`, so they display in Azure DevOps Wiki, in the mobile app, and in PDF exports.

> **Need the editable source?** The original vector `.svg` / Mermaid `.mmd` sources live in the
> repo at `flat-repo-ner/KT learning/images/`. Edit there, re-export to PNG, and re-upload the
> attachment with the same file name to update every page at once.

---

## Group A — Architecture & API call views

### 1. High-Level Architecture
The whole system as a 3-station assembly line (clean → understand → fix), with the AI cloud.
![High-Level Architecture](/.attachments/ner-kt-01-highlevel-architecture.png)

### 2. Low-Level Component / Module View
Every file, its key functions, the calls between them, and the `DEPENDENCIES` toolbox.
![Low-Level Components](/.attachments/ner-kt-02-lowlevel-components.png)

### 3. Request Flow (Block Diagram)
The `run_ner()` decision tree + pipeline, including the ⚡ fast-path that skips the AI.
![Request Flow](/.attachments/ner-kt-03-request-flow-blockdiagram.png)

### 4. UML Sequence — How the APIs are called
Time-ordered call/return between Azure ML, score.py, ner_helper, pre/post-processing and Azure OpenAI.
![Sequence UML](/.attachments/ner-kt-04-sequence-uml-api-calls.png)

### 5. Deployment View
Where things run: the Azure ML endpoint container, `.env`, `dependencies/`, and the two GPT deployments (NPROD/PROD with fallback).
![Deployment View](/.attachments/ner-kt-05-deployment-view.png)

### 6. Data-Flow View (dev pipeline)
How Snowflake / Azure SQL / Elasticsearch feed the generated dependency files that the runtime reads.
![Data Flow](/.attachments/ner-kt-06-dataflow-dev-pipeline.png)

---

## Group B — NER classes & domain knowledge

### 7. The 17 NER Entity Classes
All entity types grouped by category (identity, composition, manufacturing, certifications, context) + the out-of-scope bucket.
![NER Entity Classes](/.attachments/ner-kt-07-ner-entity-classes.png)

### 8. UML Class Diagram — output structure
The nested object types: Property/Modifier, Filler, AutoCert, RailwayCert, WaterCert, OutOfScope.
![Class Hierarchy](/.attachments/ner-kt-08-class-hierarchy-uml.png)

### 9. Materials Taxonomy (domain knowledge)
Real Celanese values: polymers, brands, fillers, features — and how a GRADE is composed from them.
![Materials Taxonomy](/.attachments/ner-kt-09-materials-taxonomy.png)

### 10. PROPERTY types & UL → PLC conversions
The three property types and the electrical-safety value→category conversions (CTI/HAI/HWI/HVAR/HVTR/Arc).
![Properties & PLC](/.attachments/ner-kt-10-properties-ul-plc-knowledge.png)

### 11. Rule-Based vs LLM — how each label is resolved
LLM-first with rule fast-paths before it and rule post-processing after it; all 17 labels categorized.
![Rule-based vs LLM](/.attachments/ner-kt-11-rulebased-vs-llm.png)

### 12. NER Approach — data, training & serving
End-to-end view of the data sources, fine-tuning loop and the serving path used for prediction.
![NER approach — data, training, serving](/.attachments/ner-kt-13-ner-approach.png)

---

| # | Attachment | View type |
|---|------------|-----------|
| 1 | `ner-kt-01-highlevel-architecture.png` | High-level block |
| 2 | `ner-kt-02-lowlevel-components.png` | Low-level component |
| 3 | `ner-kt-03-request-flow-blockdiagram.png` | Flow / block |
| 4 | `ner-kt-04-sequence-uml-api-calls.png` | UML sequence |
| 5 | `ner-kt-05-deployment-view.png` | UML deployment |
| 6 | `ner-kt-06-dataflow-dev-pipeline.png` | Data-flow |
| 7 | `ner-kt-07-ner-entity-classes.png` | Domain — entity classes |
| 8 | `ner-kt-08-class-hierarchy-uml.png` | UML class hierarchy |
| 9 | `ner-kt-09-materials-taxonomy.png` | Domain — taxonomy |
| 10 | `ner-kt-10-properties-ul-plc-knowledge.png` | Domain — properties/PLC |
| 11 | `ner-kt-11-rulebased-vs-llm.png` | Rule-based vs LLM resolution |
| 12 | `ner-kt-13-ner-approach.png` | Approach — data / training / serving |
