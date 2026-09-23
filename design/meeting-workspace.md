# Meeting workspace

Mode: Operate. The user-pinned direction remains a familiar Zoom-style application with simple controls and explicit recording state. The main route now hosts shared LAN conferences; the earlier local demonstration and sample-data generators have been removed.

## Direction contract

THESIS: Create or open a conference, join with the microphone, then explicitly enable recording and analysis. Keep the immediate action clear while making invitations, recording consent, and connection state understandable.

OWN-WORLD: Cool white and gray workspace, blue navigation and controls, orange start tile, dark call stage, system UI typography, rounded controls, and flat bordered panels. Preserve the product name Протокол without implying Zoom affiliation. No decorative imagery.

STORY: Start, join by invitation, or schedule; enter the call; invite colleagues; optionally enable camera or screen sharing; let the host start recording; review speech, assignments, and minutes; stop recording and wait for processing before export.

FIRST VIEWPORT: Horizontal navigation and four large actions: start, join, schedule, and recordings/results. A short guide sits beside the actions; recent conferences sit below. The room uses a dark prejoin/call stage beside a materials panel. Recording state appears above the room, with invitation, processing state, and meeting actions below the stage.

FORM: Extend the incumbent desktop meeting conventions in `app/conference-app.tsx`, `app/conference-room.tsx`, and `app/conference.css`. This is a functional extension, not a replacement visual identity.

## Current live surface

- Start/join dialogs collect a displayed name and explicit consent. Creation has a prefilled meeting title; scheduling adds date/time, and joining accepts an invitation. An optional creation key stays inside a disclosure.
- Prejoin explains microphone entry and optional camera/screen controls. A single primary action requests microphone access. A completed meeting instead shows its saved-materials state.
- In-call controls expose microphone, camera, screen sharing, host recording, and leave. The host can separately end the meeting for everyone. Recording and local upload status remain visible; errors, reconnecting, model unavailability, and failed processing have explicit messages.
- The adjacent material tabs are speech, assignments, summary, chat, and people. Assignments expose editing and source quotations. Summary export controls explain why recording and processing must finish first. Participant labels reflect the individual member stream and online state.
- The room uses a maximum width of 1800px and a 390px sidebar; at 1100px the sidebar becomes 350px. At 850px the room and home launcher stack, and the material panel has a bounded scroll area. At 500px video tiles stack, controls wrap compactly, and the prejoin stage has a 360px minimum height. These are current surface measurements, not new global tokens.

## Product boundaries

The live conference supports up to eight concurrent members over WebRTC. Audio and text are processed by the configured self-hosted services; trusted LAN HTTPS and usable media permissions are required. Recording is an explicit host action. Each member supplies their own microphone stream; speaker names identify that stream, not a biometric identity, and shared-screen system audio is not recorded.

Microphone access, peer media, camera, screen sharing, upload delivery, and actual model performance depend on the deployment. Recognition and analysis may queue or fail; the UI must keep those states visible. Mixed Russian/Kazakh accuracy and processing speed require tests on real hardware. A visible transcript panel is not evidence that a real model processed audio.

The app has no demonstration route or prefilled meetings. Current live capabilities and deployment boundaries are specified in `PRODUCT.md` and `CONFERENCES.md`.

## Review evidence and documentation boundary

The reviewer approved only the desktop and mobile **prejoin** surfaces captured in `.impeccable/review/conference/desktop.png` and `.impeccable/review/conference/mobile.png`. This verdict does not establish visual review of every in-call/material state or validate physical-device media, live transcription, or model quality. Follow the two-computer procedure in `CONFERENCES.md` for deployment acceptance.

The saved scan at `.impeccable/review/conference-findings.json` contains 78 advisory findings and no blocking findings: 46 color, 30 font-size, and 2 radius findings. Examples include the prejoin surface `#202735`, video/control surface `#151922`, recording/leave control `#af2738`, and additional supporting type sizes. These are reported as drift from the incumbent token documentation, not adopted into its normative palette or scales.

`DESIGN.md` and `.impeccable/design.json` are preserved for this ordinary extension. This brief records current surface behavior and review limits without silently refreshing the global design system. There are no new shipping raster assets; the two screenshots are review evidence.

## What Changed? extension

The user confirmed explicit selection of the previous meeting and a briefing intended for 30 seconds of reading. Creation offers an optional comparison with a completed meeting; the current room's host can also configure it later. Selection is limited to accessible completed meetings where the user is the host, using credentials saved in this browser. Linking requires host access to both rooms and explicit consent to share the short briefing and evidence quotations with participants in the new room. Nothing is selected by inference.

The «Что изменилось?» panel sits before the call workspace and remains usable while joining or talking. It polls independently every five seconds; pending/generating copy explicitly permits entering or continuing the call. Thirty seconds describes reading time, not model latency. The local worker prepares the result asynchronously, with a two-minute processing-attempt limit documented in `CONFERENCES.md`.

The result has at most five items and 60 words of main text: new risks, newly overdue assignments, changed decisions, and unresolved questions. Supporting category labels, dates, sources, and coverage notices sit outside that short main text. Additional omitted items are counted. Each item has a «На основании чего» disclosure with labeled quotations, timestamps when available, and previous deadline context for overdue assignments.

New overdue assignments are determined against the task snapshot saved when the previous meeting ended; already-overdue, completed, and cancelled assignments do not become new overdue findings. New risks and changed decisions need evidence from host notes about events after the meeting. The editable «Что произошло после созвона?» notes allow up to 2000 characters and are shared as source material. Open questions come from explicitly deferred questions and available updates. The feature does not monitor external systems or infer unseen progress.

First meetings show that no previous meeting is selected, and a selector with no eligible history says so. A completed comparison with no confirmed findings has its own empty state. Older meetings without a historical task snapshot disclose the missing baseline; no snapshot or task history is invented retroactively. Coverage disclosures identify incomplete source coverage. Long-meeting context prioritizes new notes and decisions, then task changes and recent speech.

Changes to source assignments invalidate prior conclusions; stale output is hidden and the panel requests an update. On entry, the host automatically refreshes a successful stale briefing once; manual refresh and saving updated notes are also available while the current meeting remains open. Model failure is explicit and can leave deterministic deadline findings available. An unavailable previous meeting has a separate message. No sample conclusions replace unavailable data.

The extension reuses the white bordered panel, blue links, red risk/deadline labels, system typography, and compact disclosures. Its panel has 24px padding, reducing to 18px below 600px; the header wraps and item columns adapt from a minimum of 280px to the available width. These describe this surface without changing the incumbent global tokens.

### What Changed? review evidence

The reviewer approved four bounded screenshots under `.impeccable/review/what-changed/`: `form-desktop.png`, `form-mobile.png`, `desktop.png`, and `mobile.png`. They cover the creation form with no previous meetings and the first-meeting empty briefing on desktop and mobile. Populated briefing output, expanded sources, stale/error/partial states, and actual model results were not screenshot-verified by this review. The verdict does not validate model quality or deployment performance.

The saved `findings.json` in that directory reports four advisory font-size findings (20px once and 13px three times), with zero blocking findings. They are recorded as documentation drift rather than silently added to the type ramp. `DESIGN.md` and `.impeccable/design.json` remain unchanged for this ordinary extension. The screenshots are review evidence, not shipping raster assets.
