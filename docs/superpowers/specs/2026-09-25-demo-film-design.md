# 8848 PDF — Demo Film — Design

## Overview

A ~70-second silent, captioned film demonstrating the pdf-ai engine, built
with Remotion and composed from **real captured frames of the real
application**, not mockups. Internal-use artifact, produced to a standard
that would survive being shown to people outside the team.

Its argument, in one line: most tools that claim to redact a PDF draw a
black box and leave the text in the file; this one removes it, and the film
proves that on camera rather than asserting it.

## Goals

- Show the product doing real work on a real document, with nothing faked.
- Land one differentiator hard — **removal is real** — rather than listing
  every feature evenly.
- Show that the natural-language path runs against a **local** model, so
  the document never leaves the machine.
- Be re-renderable later without a live server or a live model.

## Non-goals (explicit)

- **No voiceover / no audio pipeline.** Captions only. It must read muted,
  it circulates internally without an audio review, and it avoids a TTS
  dependency. Music and narration are a later decision, not this pass.
- **No interactive player, no hosting, no CI.** One composition, one render
  command, one output file.
- **No invented UI.** Every pixel of product shown is a real capture. If a
  moment cannot be captured, it is cut rather than mocked.
- **No live capture at render time.** Rendering must not require uvicorn or
  Ollama to be running.
- **Not a tutorial.** It is a demonstration, not documentation; it does not
  explain how to install or operate the tool.

## Subject matter

`webui/static/sample-document.pdf` — a fictional *Sunrise Family Clinic*
patient intake form. It carries a realistic PII payload (name, DOB, SSN
`512-34-9081`, home address, phone, emergency contact) with zero real-data
risk, and it is already bundled with the product.

It also contains a typo — "**Aprill** 12, 2026" — used deliberately as the
non-redaction beat: fixing it exercises layout-preserving `replace_text` and
shows the engine is a document editor, not just a redaction tool.

## Beat sheet

Total ~70s at 30fps (~2100 frames). Times are targets, not contracts.

| # | Beat | ~Time | Content |
|---|---|---|---|
| 1 | Title | 0–6s | 8848 Lab mark; "Document editing that actually edits the document." |
| 2 | The document | 6–16s | The real form; callouts land on the actual PII pixels. |
| 3 | The instruction | 16–32s | Real footage: plain-English instruction typed, Run pressed, terminal card showing qwen3 running locally. Beat: nothing leaves this machine. |
| 4 | **Proof** | 32–46s | Redactions land; then text extraction on the **exported** file returns nothing for the SSN. The centrepiece. |
| 5 | Beyond redaction | 46–60s | "Aprill" → "April" layout-preserving fix; image replacement; metadata sanitize. |
| 6 | Close | 60–70s | Capability summary; 8848 Lab. |

Beat 4 is the one that must land. If time pressure forces a cut, it comes
out of beat 5.

## Architecture

```
demo/
  package.json            # remotion + react + playwright (dev)
  remotion.config.ts      # render settings
  capture.mjs             # drives the REAL app, writes real frames
  src/
    Root.tsx              # composition registry
    Film.tsx              # the sequence spine
    theme.ts              # Nord tokens lifted from the real stylesheet
    scenes/               # one component per beat
    components/           # Callout, Caption, Chrome, InternalTag, ...
  public/captures/        # committed real PNGs
  out/                    # rendered video (gitignored)
```

### Capture (`capture.mjs`)

A scripted Playwright run against a live `uvicorn` + live Ollama, writing
deterministic PNGs into `public/captures/`. Run manually and **committed**,
exactly like `tests/fixtures/` — so the film renders from fixed inputs and
a later UI change regenerates them by re-running one script rather than by
hand.

Captures needed: the loaded form; the instruction mid-type; the terminal
card running; the redacted result; the typo before/after; the image
replacement before/after; the metadata panel before/after sanitize.

### Theme (`theme.ts`)

Nord tokens copied from `webui/static/styles.css`'s `:root` — `--ink
#2e3440`, `--muted #4c566a`, `--line #d8dee9`, `--paper #eceff4`, `--panel
#2e3440`, `--accent #5e81ac`, `--accent-on-dark #88c0d0`, `--danger
#bf616a`. The film must look like the product, not merely near it.

### Motion

Spring-based entrances, restrained. Captured frames are presented on a
subtle device chrome with slow scale drift so static screenshots do not
read as dead. Callouts are drawn rectangles with a connector and a label,
positioned in the captured image's own coordinate space.

**Real latency is compressed, not faked.** The local model genuinely takes
seconds; the film shows the real run with the dead time cut.

## Internal marking

A persistent, understated `INTERNAL — NOT FOR DISTRIBUTION` tag in a corner
for the whole runtime, in `--muted` at low weight. Present enough to be
honest about the artifact's status; quiet enough not to undercut it.

## Verification

- Every scene reviewed as a rendered still, by eye, at 1920×1080 — the same
  discipline the image-replacement work used, where a caption was
  truncated by CSS and only looking caught it.
- The final file plays start to finish, with no dropped or black frames.
- The proof beat's extraction output is copied from a **real** run against
  the real exported file, not typed by hand.

## Out of scope

Voiceover, music, subtitles beyond the on-screen captions, multiple aspect
ratios, a landing-page embed, and any capture of a document other than the
bundled sample.
