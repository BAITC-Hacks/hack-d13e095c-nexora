# Product

<!-- impeccable:product-schema 1 -->

## Platform
web

## Users and purpose
Russian-speaking team members recording meetings and preparing minutes. The user explicitly prioritizes starting a recording quickly, with large buttons and an understandable meeting screen.

## Operating context
Docker runs Caddy HTTPS, React frontend, FastAPI, PostgreSQL and a persistent live worker. Ollama runs on a separate LAN computer. Self-hosted Whisper can run on either server. Clients need a trusted HTTPS certificate to use media over LAN.

## Capabilities and constraints
The main route provides shared WebRTC conferences (up to 8 concurrent members), camera, screen sharing, chat, explicit recording, per-member audio transcription, incremental local analysis, editable assignments, reminders while open and PDF/DOCX/WAV export. Invitations and credentials are capability based, stored in the user's browser. The application has no demo route, seeded meetings or simulated recognition. Empty states remain until real user activity. Real-model speed and mixed-language recognition must be evaluated on the deployment hardware. Speaker labels come from individual member streams, not voice biometrics. See CONFERENCES.md for deployment and test procedure.

## Brand commitments
Product name: Протокол. User requests the familiar interface and workflow of Zoom, with clear, simple controls. Preserve the product name; do not imply affiliation with Zoom.

## Product principles
- Start a meeting without completing a long form.
- Make recording state and the stop action unmistakable.
- Keep all existing recording, document and task functions available.
- Show real service errors and empty states; never substitute generated sample data.

## Pre-meeting change briefing
What Changed? links an explicitly selected previous completed meeting to a follow-up. Hosts of both rooms authorize sharing short evidence quotes with new participants. The worker combines deterministic newly overdue assignments with local-model-supported new risks, changed decisions and unresolved questions. Host notes supply events outside the system. At most five items and 60 main-text words target 30 seconds of reading. Empty, stale, incomplete and model-error states are explicit; historical task state is never retroactively invented. Calls do not wait for the briefing.

## Corporate Memory Graph
The user confirmed a shared all-team map across saved meetings, with projects and document mentions extracted by local Ollama. Seven object kinds connect people, tasks, projects, decisions, deadlines, documents, and meetings to source quotations. Project/document names group only by exact normalized name (case and excess whitespace); people with the same name remain separate meeting identities. Documents mentioned in speech are not uploaded files. AI extraction requires source support and can be incomplete or unavailable.

Read access to all saved meeting discussions is controlled by the shared `MEMORY_ACCESS_KEY`, falling back to `CONFERENCE_ACCESS_KEY`; if both are empty, anyone able to reach the site can read the map. This access does not grant call entry or editing rights. Calls still require their invitations/credentials. The UI must make the all-team sharing scope explicit and retain source, archive, partial-coverage, indexing, and error notices.
