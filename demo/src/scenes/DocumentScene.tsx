import React from 'react'
import { interpolate, staticFile, useCurrentFrame } from 'remotion'
import { color, size, type } from '../theme'
import { Caption, Eyebrow, InternalTag, Stage, useEnter } from '../components/primitives'
import { AnnotatedShot, Highlight } from '../components/Callout'

/**
 * Coordinates measured against the real capture (page-before.png, 1224x1586),
 * expressed as fractions so they survive any resizing of the shot.
 */
const PII = [
  { box: { x: 0.113, y: 0.228, w: 0.24, h: 0.031 }, label: 'date of birth', delay: 26 },
  { box: { x: 0.113, y: 0.266, w: 0.36, h: 0.031 }, label: 'social security number', delay: 40 },
  { box: { x: 0.113, y: 0.343, w: 0.30, h: 0.031 }, label: 'phone', delay: 54 },
  { box: { x: 0.113, y: 0.381, w: 0.485, h: 0.031 }, label: 'emergency contact', delay: 68 },
]

export const DocumentScene: React.FC = () => {
  const frame = useCurrentFrame()
  const enter = useEnter(0, 150)
  const scale = interpolate(frame, [0, 300], [1, 1.035]) // slow push in

  return (
    <Stage>
      <div
        style={{
          position: 'absolute',
          left: size.gutter,
          top: 92,
          opacity: enter,
        }}
      >
        <Eyebrow>The document</Eyebrow>
        <div
          style={{
            marginTop: 16,
            fontSize: type.title,
            fontWeight: 700,
            letterSpacing: -1.4,
            maxWidth: 760,
            lineHeight: 1.12,
          }}
        >
          A patient intake form, full of the things you must not ship.
        </div>
        <div
          style={{
            marginTop: 22,
            fontSize: type.body,
            color: color.muted,
            maxWidth: 680,
            lineHeight: 1.5,
          }}
        >
          Name, date of birth, social security number, address, phone, next of kin — on
          one page, in a file that gets emailed.
        </div>
      </div>

      <div
        style={{
          position: 'absolute',
          right: size.gutter,
          top: '50%',
          transform: `translateY(-50%) scale(${scale})`,
          opacity: enter,
        }}
      >
        {/* page-before.png is 1224x1586; the form ends around 55% down, so the
            rest is blank paper. Crop it away rather than showing half an
            empty page. Highlight coordinates stay in source fractions. */}
        <AnnotatedShot
          src={staticFile('captures/page-before.png')}
          width={720}
          aspect={1586 / 1224}
          crop={[0.06, 0.45]}
        >
          {PII.map((p) => (
            <Highlight key={p.label} box={p.box} label={p.label} delay={p.delay} side="left" />
          ))}
        </AnnotatedShot>
      </div>

      <Caption delay={80}>
        Sensitive fields, identified on the real document — nothing here is a mockup.
      </Caption>
      <InternalTag />
    </Stage>
  )
}
