import React from 'react'
import { interpolate, staticFile, useCurrentFrame } from 'remotion'
import { color, font, size, type } from '../theme'
import {
  Caption,
  Eyebrow,
  InternalTag,
  Stage,
  useEnter,
  useTypedText,
} from '../components/primitives'
import proof from '../../public/captures/proof.json'

const INSTRUCTION = proof.instruction as string

/** Left column holds the interaction; right column holds the document. */
const COL = 1060
const SHOT = 560

export const InstructionScene: React.FC = () => {
  const frame = useCurrentFrame()
  const enter = useEnter(0, 150)
  const typed = useTypedText(INSTRUCTION, 18, 1.5)
  const caretOn = Math.floor(frame / 8) % 2 === 0

  // The real run took ~98s on a local 14B model. The footage is real; the
  // waiting is compressed, because 98 seconds of a spinner is not a film.
  const runStart = 150
  const doneAt = 300
  const running = frame >= runStart && frame < doneAt
  const done = frame >= doneAt

  const resultEnter = useEnter(doneAt, 160)
  const swap = useEnter(doneAt + 6, 160)

  return (
    <Stage>
      <div style={{ position: 'absolute', left: size.gutter, top: 76, opacity: enter }}>
        <Eyebrow>The instruction</Eyebrow>
        <div
          style={{
            marginTop: 12,
            fontSize: 52,
            fontWeight: 700,
            letterSpacing: -1.4,
            maxWidth: COL,
            lineHeight: 1.12,
          }}
        >
          You say what to remove. In plain English.
        </div>
      </div>

      {/* The command line, in the product's own styling, typing the
          instruction that was genuinely sent to the model. */}
      <div style={{ position: 'absolute', left: size.gutter, top: 258, width: COL, opacity: enter }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 14,
            background: color.panel,
            border: `1px solid ${color.panelBorder}`,
            borderRadius: 12,
            padding: '20px 24px',
            boxShadow: '0 24px 56px rgba(46,52,64,0.22)',
          }}
        >
          <span style={{ fontFamily: font.mono, fontSize: 22, color: color.accentOnDark }}>$</span>
          <span
            style={{
              fontFamily: font.mono,
              fontSize: 21,
              color: color.paper,
              whiteSpace: 'nowrap',
              overflow: 'hidden',
            }}
          >
            {typed}
            {!done && caretOn ? <span style={{ color: color.accentOnDark }}>▋</span> : null}
          </span>
        </div>

        <div style={{ display: 'flex', gap: 12, marginTop: 18, alignItems: 'center' }}>
          {['Anthropic', 'OpenAI-compatible', 'Ollama (local)'].map((p) => {
            const active = p.startsWith('Ollama')
            return (
              <div
                key={p}
                style={{
                  fontSize: 19,
                  fontWeight: 600,
                  padding: '8px 15px',
                  borderRadius: 999,
                  border: `1px solid ${active ? color.accent : color.line}`,
                  background: active ? color.accent : 'transparent',
                  color: active ? color.white : color.muted,
                }}
              >
                {p}
              </div>
            )
          })}
          <div style={{ fontSize: 19, color: color.muted, marginLeft: 6 }}>
            model{' '}
            <strong style={{ fontFamily: font.mono, color: color.ink }}>{proof.model}</strong>
          </div>
        </div>
      </div>

      {/* The real terminal card: mid-run, then the real finished summary. */}
      <div style={{ position: 'absolute', left: size.gutter, top: 430, width: COL }}>
        {running ? (
          <>
            <img
              src={staticFile('captures/terminal-running.png')}
              style={{
                width: '100%',
                display: 'block',
                borderRadius: 12,
                boxShadow: '0 20px 48px rgba(46,52,64,0.20)',
              }}
            />
            <div
              style={{
                marginTop: 18,
                fontSize: 25,
                color: color.muted,
                display: 'flex',
                alignItems: 'center',
                gap: 12,
              }}
            >
              <span
                style={{
                  width: 9,
                  height: 9,
                  borderRadius: 5,
                  background: color.warn,
                  opacity: Math.floor(frame / 6) % 2 === 0 ? 1 : 0.3,
                }}
              />
              Running on this machine. Nothing is uploaded.
            </div>
          </>
        ) : null}

        {done ? (
          <div
            style={{
              opacity: resultEnter,
              transform: `translateY(${interpolate(resultEnter, [0, 1], [16, 0])}px)`,
            }}
          >
            <img
              src={staticFile('captures/terminal-done.png')}
              style={{
                width: '100%',
                display: 'block',
                borderRadius: 12,
                boxShadow: '0 20px 48px rgba(46,52,64,0.20)',
              }}
            />
          </div>
        ) : null}
      </div>

      {/* The document, before and after, so the frame is never half empty. */}
      <div
        style={{
          position: 'absolute',
          right: size.gutter,
          top: 236,
          width: SHOT,
          opacity: enter,
        }}
      >
        <div
          style={{
            position: 'relative',
            width: SHOT,
            height: SHOT * (1586 / 1224) * 0.54,
            borderRadius: 12,
            overflow: 'hidden',
            background: color.white,
            border: `1px solid ${color.line}`,
            boxShadow: '0 26px 60px rgba(46,52,64,0.18)',
          }}
        >
          <img
            src={staticFile('captures/page-before.png')}
            style={{
              position: 'absolute',
              width: '100%',
              top: -0.06 * SHOT * (1586 / 1224),
              opacity: 1 - swap,
            }}
          />
          <img
            src={staticFile('captures/page-after.png')}
            style={{
              position: 'absolute',
              width: '100%',
              top: -0.06 * SHOT * (1586 / 1224),
              opacity: swap,
            }}
          />
        </div>
        <div
          style={{
            marginTop: 14,
            fontSize: 19,
            color: color.muted,
            fontFamily: font.mono,
            textAlign: 'right',
          }}
        >
          {done ? 'after' : 'before'}
        </div>
      </div>

      <Caption delay={16}>
        {done
          ? `The model chose the operations; the engine applied them — ${proof.elapsedSeconds}s, offline.`
          : 'One sentence. No coordinates, no field names, no configuration.'}
      </Caption>
      <InternalTag />
    </Stage>
  )
}
