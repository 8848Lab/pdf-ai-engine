import React from 'react'
import { interpolate, staticFile, useCurrentFrame } from 'remotion'
import { color, font, size, type } from '../theme'
import { Caption, Eyebrow, InternalTag, Stage, Terminal, useEnter } from '../components/primitives'
import comparison from '../../public/captures/proof-comparison.json'

const SSN = '512-34-9081'

const Panel: React.FC<{
  src: string
  heading: string
  sub: string
  tone: 'danger' | 'ok'
  delay: number
  result: React.ReactNode
}> = ({ src, heading, sub, tone, delay, result }) => {
  const enter = useEnter(delay, 170)
  const stroke = tone === 'danger' ? color.danger : color.ok
  return (
    <div
      style={{
        width: 800,
        opacity: enter,
        transform: `translateY(${interpolate(enter, [0, 1], [26, 0])}px)`,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
        <div style={{ fontSize: 30, fontWeight: 700, letterSpacing: -0.6 }}>{heading}</div>
      </div>
      <div style={{ fontSize: 21, color: color.muted, marginTop: 6, minHeight: 52 }}>{sub}</div>

      <div
        style={{
          marginTop: 18,
          borderRadius: 12,
          overflow: 'hidden',
          border: `1px solid ${color.line}`,
          background: color.white,
          boxShadow: '0 22px 50px rgba(46,52,64,0.16)',
          height: 410,
        }}
      >
        <img
          src={src}
          style={{ width: '100%', display: 'block', marginTop: '-6%' }}
        />
      </div>

      <div
        style={{
          marginTop: 18,
          border: `1px solid ${stroke}55`,
          background: `${stroke}12`,
          borderRadius: 10,
          padding: '16px 18px',
        }}
      >
        {result}
      </div>
    </div>
  )
}

export const ProofScene: React.FC = () => {
  const frame = useCurrentFrame()
  const enter = useEnter(0, 150)

  const naiveLeaks = comparison.naive_blackbox[SSN]
  const engineLeaks = comparison.engine[SSN]

  return (
    <Stage>
      <div style={{ position: 'absolute', left: size.gutter, top: 68, opacity: enter }}>
        <Eyebrow>The part that matters</Eyebrow>
        <div
          style={{
            marginTop: 12,
            fontSize: 54,
            fontWeight: 700,
            letterSpacing: -1.5,
            lineHeight: 1.1,
            maxWidth: 1400,
          }}
        >
          Both of these look redacted. Only one of them is.
        </div>
      </div>

      <div
        style={{
          position: 'absolute',
          left: size.gutter,
          top: 236,
          display: 'flex',
          gap: 88,
        }}
      >
        <Panel
          src={staticFile('captures/compare-naive.png')}
          heading="A black box drawn over it"
          sub="What most PDF tools do, and what most people think redaction is."
          tone="danger"
          delay={18}
          result={
            <div style={{ fontFamily: font.mono, fontSize: 21, lineHeight: 1.6 }}>
              <div style={{ color: color.muted }}>$ copy the text out</div>
              <div style={{ color: color.danger, fontWeight: 700, marginTop: 6 }}>
                {naiveLeaks ? `→ ${SSN}` : '→ nothing'}
              </div>
              <div style={{ color: color.muted, marginTop: 6, fontSize: 18 }}>
                still in the file, fully recoverable
              </div>
            </div>
          }
        />

        <Panel
          src={staticFile('captures/compare-engine.png')}
          heading="8848 PDF"
          sub="The content is removed from the document, not covered up."
          tone="ok"
          delay={54}
          result={
            <div style={{ fontFamily: font.mono, fontSize: 21, lineHeight: 1.6 }}>
              <div style={{ color: color.muted }}>$ copy the text out</div>
              <div style={{ color: color.ok, fontWeight: 700, marginTop: 6 }}>
                {engineLeaks ? `→ ${SSN}` : '→ nothing'}
              </div>
              <div style={{ color: color.muted, marginTop: 6, fontSize: 18 }}>
                gone from the exported file
              </div>
            </div>
          }
        />
      </div>

      <Caption delay={96}>
        Both files were produced from the same source and read the same way — by selecting
        and copying, exactly as a recipient would.
      </Caption>
      <InternalTag />
    </Stage>
  )
}
