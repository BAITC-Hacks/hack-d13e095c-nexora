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
