/**
 * Design tokens lifted verbatim from the product's own stylesheet
 * (webui/static/styles.css :root). The film has to look like the thing it
 * is showing, not merely near it -- so these are copied, not re-picked.
 */
export const color = {
  ink: '#2e3440',
  muted: '#4c566a',
  line: '#d8dee9',
  paper: '#eceff4',
  panel: '#2e3440',
  panel2: '#3b4252',
  panelBorder: '#434c5e',
  accent: '#5e81ac',
  accentOnDark: '#88c0d0',
  danger: '#bf616a',
  ok: '#a3be8c',
  warn: '#ebcb8b',
  white: '#ffffff',
} as const

export const font = {
  sans:
    '-apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, "Helvetica Neue", Arial, sans-serif',
  mono: '"SF Mono", "Cascadia Code", "Fira Code", Consolas, "Liberation Mono", monospace',
} as const

/** 1920x1080. Sizes below are tuned for that canvas. */
export const size = {
  width: 1920,
  height: 1080,
  gutter: 96,
} as const

export const type = {
  hero: 96,
  title: 64,
  section: 44,
  body: 30,
  caption: 26,
  label: 20,
  mono: 24,
} as const

/** The film's spine, in frames at 30fps. One place to retime everything. */
export const FPS = 30
const s = (seconds: number) => Math.round(seconds * FPS)

export const scenes = {
  title: { from: 0, duration: s(6) },
  document: { from: s(6), duration: s(10) },
  instruction: { from: s(16), duration: s(16) },
  proof: { from: s(32), duration: s(14) },
  beyond: { from: s(46), duration: s(12) },
  close: { from: s(58), duration: s(10) },
} as const

export const TOTAL_FRAMES = scenes.close.from + scenes.close.duration
