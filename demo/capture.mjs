/**
 * Captures REAL frames of the REAL application for the demo film.
 *
 * Run manually, with a live server and a live Ollama:
 *   cd .. && ./.venv/Scripts/python.exe -m uvicorn webui.main:app --port 8130
 *   cd demo && npm run capture
 *
 * Writes PNGs into public/captures/ and a real (not hand-typed) extraction
 * result into public/captures/proof.json. Those outputs are committed, so
 * rendering the film never needs a server or a model running -- same
 * discipline as the repo's checked-in test fixtures.
 *
 * Nothing here composes or beautifies. It drives the product and records
 * what the product actually showed.
 */
import { chromium } from 'playwright'
import { mkdir, writeFile, rm } from 'node:fs/promises'
import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import path from 'node:path'
import os from 'node:os'

const run = promisify(execFile)

const BASE = process.env.DEMO_BASE_URL ?? 'http://127.0.0.1:8130'
const MODEL = process.env.DEMO_MODEL ?? 'qwen3:14b'
const INSTRUCTION =
  "redact the patient's social security number, date of birth and phone number"

const OUT = path.resolve('public/captures')
const REPO = path.resolve('..')
const PY = path.join(REPO, '.venv/Scripts/python.exe')

const shot = async (target, name, opts = {}) => {
  await target.screenshot({ path: path.join(OUT, `${name}.png`), ...opts })
  console.log(`  captured ${name}.png`)
}

/** Upload a file through the real upload endpoint, then re-sync the page. */
const load = async (page, absPath) => {
  await page.setInputFiles('#file-input', absPath)
  // Note the explicit `null`: waitForFunction is (fn, arg, options), so an
  // options object in the second slot is silently taken as the argument and
  // the timeout quietly stays at the 30s default.
  await page.waitForFunction(() => document.querySelectorAll('.page').length > 0, null, {
    timeout: 20000,
  })
  await page.waitForTimeout(600) // let the page PNG finish decoding
}

const main = async () => {
  await mkdir(OUT, { recursive: true })

  const browser = await chromium.launch()
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
    deviceScaleFactor: 2, // retina captures, so scaling up in the film stays sharp
  })

  const health = await page.goto(BASE, { waitUntil: 'domcontentloaded' }).catch(() => null)
  if (!health) {
    throw new Error(
      `Could not reach ${BASE}. Start the app first:\n` +
        `  cd .. && ./.venv/Scripts/python.exe -m uvicorn webui.main:app --port 8130`
    )
  }

  const sample = path.join(REPO, 'webui/static/sample-document.pdf')

  // ---- Beat 2/3/4: the AI redaction, start to finish -------------------
  console.log('phase A: AI redaction on the sample document')
  await load(page, sample)
  await shot(page.locator('.page img').first(), 'page-before')

  // Provider + model, through the real controls.
  await page.click('.provider-option[data-provider="ollama"]')
  await page.click('.advanced-fields summary')
  await page.fill('#model-input', MODEL)
  await page.click('.advanced-fields summary') // collapse again, so it is not in shot

  // Type it like a person would, so the capture shows a real command line.
  await page.click('#instruction-input')
  await page.type('#instruction-input', INSTRUCTION, { delay: 18 })
  // Not `.instruct-panel` alone -- that also matches the metadata panel and
  // the hidden manual-controls insert panel. Pick the one that owns the
  // command line.
  const aiPanel = page.locator('.instruct-panel').filter({ has: page.locator('#instruction-input') })
  await shot(aiPanel, 'command-typed')

  const started = Date.now()
  await page.click('#ai-instruct-button')
  await page.waitForSelector('#terminal-card:not([hidden])', { timeout: 10000 })
  await page.waitForTimeout(400)
  await shot(page.locator('#terminal-card'), 'terminal-running')

  // A local 14B model genuinely takes a while. Wait for the real result.
  await page.waitForFunction(
    () => {
      const t = document.getElementById('terminal-title')
      return t && (t.textContent === 'done' || t.textContent === 'failed')
    },
    null,
    { timeout: 600000 }
  )
  const elapsedMs = Date.now() - started
  const status = await page.textContent('#terminal-title')
  console.log(`  model finished in ${(elapsedMs / 1000).toFixed(1)}s with status: ${status}`)
  if (status !== 'done') {
    const err = await page.textContent('.terminal-result-text')
    throw new Error(`The AI run failed, refusing to capture a broken take: ${err}`)
  }

  await page.waitForTimeout(800)
  await shot(page.locator('#terminal-card'), 'terminal-done')
  await shot(page.locator('.page img').first(), 'page-after')

  const summary = (await page.textContent('.terminal-result-text'))?.trim() ?? ''

  // ---- The proof beat: real extraction against the real exported file ----
  console.log('phase A2: exporting and extracting, for the proof beat')
  const pdf = await page.evaluate(async () => {
    const res = await fetch('/api/export')
    const buf = await res.arrayBuffer()
    return Array.from(new Uint8Array(buf))
  })
  const exported = path.join(OUT, 'redacted.pdf')
  await writeFile(exported, Buffer.from(pdf))

  const probe = `
import json, sys
import pymupdf as fitz
needles = ["512-34-9081", "03/14/1985", "(208) 555-0173"]
out = {}
for label, p in (("original", sys.argv[1]), ("redacted", sys.argv[2])):
    d = fitz.open(p)
    text = "".join(pg.get_text() for pg in d)
    raw = open(p, "rb").read()
    out[label] = {
        n: {"in_text": n in text, "in_raw_bytes": n.encode() in raw} for n in needles
    }
    d.close()
print(json.dumps(out, indent=2))
`
  // Temp file, not an artifact: written outside the captures directory and
  // removed, so it never lands in the committed fixture set.
  const probeFile = path.join(os.tmpdir(), `pdf-ai-demo-probe-${process.pid}.py`)
  await writeFile(probeFile, probe)
  const { stdout } = await run(PY, [probeFile, sample, exported], { cwd: REPO })
  await rm(probeFile, { force: true })
  const proof = JSON.parse(stdout)
  console.log('  extraction result:', JSON.stringify(proof.redacted))

  // ---- Beat 5a: the typo, fixed with layout-preserving replacement ------
  console.log('phase B: layout-preserving text replacement')
  await load(page, sample)
  const typo = await page.evaluate(async () => {
    const state = await (await fetch('/api/state')).json()
    const block = state.blocks.find((b) => b.text.includes('Aprill'))
    if (!block) return null
    const res = await fetch('/api/replace', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ block_id: block.id, new_text: block.text.replace('Aprill', 'April') }),
    })
    return { ok: res.ok, before: block.text }
  })
  if (!typo?.ok) throw new Error('typo replacement failed; refusing to fake it')
  await page.evaluate(() => refreshState())
  await page.waitForTimeout(700)
  await shot(page.locator('.page img').first(), 'page-typo-fixed')

  // ---- Beat 5b: metadata sanitize, on a document that actually has some --
  console.log('phase C: metadata sanitize')
  await load(page, path.join(REPO, 'tests/fixtures/sanitize_target.pdf'))
  await page.waitForTimeout(400)
  await shot(page.locator('#metadata-panel'), 'metadata-before')
  await page.click('#sanitize-button')
  await page.waitForTimeout(1200)
  await shot(page.locator('#metadata-panel'), 'metadata-after')

  await writeFile(
    path.join(OUT, 'proof.json'),
    JSON.stringify(
      {
        capturedAt: new Date().toISOString(),
        model: MODEL,
        instruction: INSTRUCTION,
        elapsedSeconds: Number((elapsedMs / 1000).toFixed(1)),
        modelSummary: summary,
        extraction: proof,
        typoBefore: typo.before,
      },
      null,
      2
    )
  )
  console.log('  wrote proof.json')

  await browser.close()
  console.log('\ndone. Captures are in public/captures/.')
}

main().catch((err) => {
  console.error('\ncapture failed:', err.message)
  process.exit(1)
})
