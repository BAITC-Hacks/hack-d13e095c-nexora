---
name: "Протокол"
description: "Familiar meeting controls for quick local audio recording."
colors:
  primary: "#2563eb"
  primary-hover: "#1d4ed8"
  start: "#e85b24"
  start-hover: "#c94715"
  background: "#f7f8fa"
  surface: "#fff"
  foreground: "#24272d"
  muted-foreground: "#626a78"
  border: "#e3e6ec"
  input-border: "#cdd2dc"
  accent: "#edf3ff"
  accent-foreground: "#1e55c5"
  focus: "#7399ef"
  stage: "#20232b"
  stage-toolbar: "#16191f"
  stage-muted: "#bbc3d1"
  destructive: "#b42332"
  destructive-hover: "#921b28"
  badge-background: "#eff3fb"
  badge-foreground: "#637caa"
typography:
  headline:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif"
    fontSize: "clamp(25px, 2.5vw, 32px)"
    fontWeight: 650
    lineHeight: 1.25
    letterSpacing: "-0.025em"
  title:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif"
    fontSize: "17px"
    fontWeight: 650
    letterSpacing: "-0.015em"
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.5
  button:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif"
    fontSize: "14px"
    fontWeight: 550
  label:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif"
    fontSize: "12px"
  clock:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif"
    fontSize: "52px"
    fontWeight: 450
    lineHeight: 1.1
    letterSpacing: "-2px"
rounded:
  badge: "5px"
  control: "8px"
  navigation: "9px"
  panel: "12px"
  stage: "14px"
  dialog: "16px"
  launcher: "24px"
spacing:
  xs: "8px"
  sm: "12px"
  md: "16px"
  lg: "20px"
  xl: "24px"
  section: "32px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    typography: "{typography.button}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "#2559be"
    typography: "{typography.button}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
  button-stop:
    backgroundColor: "{colors.destructive}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "10px 14px"
  button-stop-hover:
    backgroundColor: "{colors.destructive-hover}"
  input:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "10px 12px"
  navigation-active:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.accent-foreground}"
    rounded: "{rounded.navigation}"
    padding: "10px 14px"
  badge:
    backgroundColor: "{colors.badge-background}"
    textColor: "{colors.badge-foreground}"
    rounded: "{rounded.badge}"
    padding: "5px 9px"
  panel:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.panel}"
  launcher-start:
    backgroundColor: "{colors.start}"
    textColor: "{colors.surface}"
    rounded: "{rounded.launcher}"
    width: "86px"
    height: "86px"
  record-stage:
    backgroundColor: "{colors.stage}"
    textColor: "{colors.surface}"
    padding: "20px"
---

# Design System: Протокол

## Overview

**Creative North Star: "The Familiar Meeting Room"**

Протокол uses familiar Zoom-style desktop conventions: a cool, quiet workspace, clear blue controls, an orange meeting launcher, and a charcoal recording stage. System typography and generous action targets make starting a local recording immediately understandable.

The product keeps its own name and uses concise Russian labels. Recording state, unavailable microphone access, local storage, planned participants, and demonstration documents must remain legible at the point where they affect a decision.

**Key Characteristics:**

- Cool white and gray surfaces with blue navigation.
- Orange start action and a dark recording stage.
- Flat bordered panels, visible focus, and compact supporting text.

## Colors

The palette uses cool neutrals and clear functional accents. Normative values are in the frontmatter, extracted from `app/redesign.css` and the inherited badge styles in `app/globals.css`.

### Primary

Meeting Blue drives primary actions, selected navigation, field focus, and document tabs. Pale Blue marks selected or supporting surfaces.

### Secondary

Start Orange distinguishes the immediate meeting launcher. Stop Red identifies the recording stop action; related red controls identify leaving the room. These roles always retain text labels.

### Neutral

Workspace Gray surrounds White surfaces. Charcoal and the deeper toolbar tone establish the recording area. Muted Slate supports descriptions and placeholders without competing with titles. Border Gray separates panels; the darker input border identifies editable fields.

## Typography

Use the system sans stack for every role. The headline is compact and moderately bold; titles remain close to body scale. Supporting UI commonly uses 12–15px text. Launcher labels use 16px at weight 600. Clock and recording duration use tabular numerals; stage duration is 30px. Avoid uppercase display treatments; the former eyebrow treatment is hidden.

## Layout

A horizontal header has an 84px minimum height. Standard content is centered at a maximum width of 1120px with 42px 36px 22px padding. The meeting workspace expands to 1480px. The home launcher pairs a two-column action group with a 370px schedule panel and a 68px gap. The room pairs a flexible stage with a 340px document panel, separated by 18px; document tabs can expand to a 0.9fr/1.1fr split.

At 1100px, gaps tighten and the room sidebar becomes 310px. At 800px, navigation wraps, content padding becomes 28px 20px 20px, and the room stacks into one column. Fields become 16px to retain mobile readability. At 500px, schedule content stacks, launcher icons shrink to 76px, recording buttons occupy the full row, and assignment rows become labeled blocks. The stage minimum height is 400px, reducing to 330px at 800px. Print hides navigation and recording controls, allowing documents to occupy the page.

## Elevation & Depth

The workspace uses tonal separation and thin borders. Primary buttons and main panels explicitly have no shadow. Dialogs retain the shared component's shadow-lg elevation and dark translucent overlay. Do not extend modal elevation to ordinary workspace panels.

## Shapes

Controls use gently rounded corners; panels are more spacious, with larger radii for dialogs and schedule cards. Launcher tiles have the most rounded square silhouette. Microphone and recording status indicators are circular. Use simple line icons and color blocks; no raster imagery is needed.

## Components

### Buttons

Primary and secondary buttons have a 42px minimum height; recording controls use 44px. Primary hover deepens blue, secondary hover uses Pale Blue, and stop hover deepens red. Keyboard focus uses a 3px outline with 3px offset. Disabled controls show an unavailable cursor; the disabled recording action uses an opaque muted dark surface. Button color transitions last 0.18s. The orange launcher lifts 3px on hover and returns on press. Reduced motion disables animation and transitions.

### Inputs / Fields

White fields use the input border, control radius, and 10px 12px padding. Muted Slate placeholders stay readable. Focus changes the border to Meeting Blue without a shadow. Search focus surrounds the whole search field with a 2px outline and 2px offset.

### Navigation

Icon-over-label destinations use compact 12px labels and a pale selected surface. A textual count sits in a small red badge where needed. Mobile navigation shares the available row; document tabs stay in their adjacent panel and use blue active text.

### Chips

Compact badges use 5px 9px padding, 11px text, and modest corners. Existing blue, green, orange, and red variants express document and task status; always retain the status wording.

### Cards / Containers

White bordered panels group lists and documents. Schedule cards have a pale blue clock area and a separated meeting list. Containers use flat surfaces; avoid adding further ornamental nesting.

### Recording stage

The charcoal stage places status at the top, a circular microphone and explanatory message in the center, and the local-device label above a darker toolbar. Show an unavailable microphone message when recording cannot run, and keep the HTTPS/localhost explanation visible. The stop action replaces start while recording. Planned participants and demonstration documents remain explicitly labeled. Playback and download appear beneath the controls once audio exists.

## Do's and Don'ts

### Do:

- Do keep recording state and the stop control unmistakable.
- Do pair status color with a readable label.
- Do preserve visible keyboard focus and reduced-motion behavior.
- Do label planned participants, local recordings, and demonstration output accurately.

### Don't:

- Don't imply shared calls, live remote participants, or actual audio transcription.
- Don't add decorative imagery or replace the familiar meeting controls with a marketing layout.
- Don't use the old warm olive visual direction.

## Live conference implementation
The main route now uses the shared server conference flow in `conference-app.tsx`, `conference-room.tsx` and `conference.css`. The former demo route and seeded-data generators have been removed. The live UI exposes real connection, recording, upload, model-health and analysis states. See PRODUCT.md and CONFERENCES.md for current capabilities; earlier local-recording notes are historical.
