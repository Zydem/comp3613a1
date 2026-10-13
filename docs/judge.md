# student-judge competency report

**Student / session:** FastStarter Student
**Artifact:** Guide chat summaries and current project report evidence for the Student Awards build
**Phases in evidence:** 1–6 (COMP 3613; Phase 5 polish, Phase 6 deploy; never generic 0–5)

**Judged at:** 2026-10-12T00:00:00Z
**Evidence pass:** re-read current report, design artefacts, and Guide summary transcripts; prior judge content ignored

## Summary

This build shows strong engagement across the full COMP 3613 flow. The student clearly framed the project, owned the workflows and model decisions, produced a complete wireframe set, verified the app in practice, and completed the required deployment step. The project also kept the implementation aligned to the layer structure and the assignment-specific requirements for claim approval, milestones, rewards, and staff review.

## Rubric scores

| ID | Metric | Score | Notes |
| --- | --- | ---: | --- |
| M1 | Phase discipline | 4 | Design was phased and the app was not shipped before the wireframe/model work was in place; Phase 5 polish preceded the deployment phase. |
| M2 | Problem framing | 4 | Student named the three workflows and kept the project scope to Student Awards with clear use-case boundaries. |
| M3 | Decision ownership | 4 | The student owned the workflow choices, reward/claim rules, and model assumptions rather than accepting a generic starter app. |
| M4 | Artefact-before-code | 4 | The report embeds the use-case diagram, model diagram, and wireframe set, and the app follows those designs. |
| M5 | Verification habit | 4 | The project verified the real behavior through the test suite and the live health check, then continued with polish and deployment. |
| M6 | Assignment fit | 4 | Thin route/service/repository layers were respected and the app reused the starter FastStarter patterns appropriately. |
| M7 | Slice explanation | 4 | The work was explained through the named workflows, model decisions, and final architecture choices, with strong alignment to services and repositories. |
| M8 | Prompt quality | 4 | The session stayed focused on named workflows, fix requests, and polish rather than a broad generic build prompt. |
| M9 | Response to pushback | 4 | The student iterated on approval rules, reward stock logic, proof handling, and confirmation flow until the final behavior matched the design. |
| M10 | Integrity | 4 | No sign of edited course skills or outside laundering concerns in the available evidence. |
| M11 | Provenance continuity | 4 | The delivered app clearly grows from the same workflow set and domain model discussed in the project. |
| M12 | Sincerity trajectory | 4 | The session shows steady engagement and a healthy path from design to verification and deployment. |

### Evidence quotes

- “Student Awards” — project scope confirmed in the design phase and kept throughout the build.
- “approval should always add 10 points per approved hour” — this shows the student owned the core business rule and refined it mid-build.
- “Redeem should open a confirmation step like W3-2 instead of redeeming straight away” — direct evidence of workflow and UX alignment with the wireframe.
- “add these images to the rewards respectively” — evidence of the visual polish required by the assignment.
- “Phase 6: deploy a Render Postgres database and the web service with the Render MCP” — explicit deployment gate handled in the correct phase.
- “python -m pytest -q” and “Invoke-WebRequest -Uri 'https://faststarter-961m.onrender.com/health'” — objective verification through the real app.

## Phase performance

- Phase 1: met — project name and named workflows were set clearly.
- Phase 2: met — use-case framing and include/extend logic were handled.
- Phase 3: met — core entities and relationships were set and documented.
- Phase 4: met — wireframes cover the required workflows and were embedded in the report.
- Phase 5: met — theme, build, and polish were all completed, with verification and workflow tuning.
- Phase 6: met — Render Postgres and web service were deployed, seeded, and the public URL was recorded.

## Totals

- Awarded total: 48 / 48
- Overall: 4.0 / 4
- Impression mark: 20 / 20

> This report is based on the final project artefacts and the available project evidence; it represents the current build state rather than any stale earlier draft.
