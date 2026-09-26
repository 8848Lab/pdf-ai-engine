import React from 'react'
import { interpolate, useCurrentFrame } from 'remotion'
import { color, font, size, type } from '../theme'
import { InternalTag, Stage, useEnter } from '../components/primitives'

export const Title: React.FC = () => {
  const frame = useCurrentFrame()
  const mark = useEnter(0, 140)
  const line1 = useEnter(10, 160)
  const line2 = useEnter(20, 160)
  const rule = useEnter(30, 200)

  // A very slow drift so the frame is never completely static.
  const drift = interpolate(frame, [0, 180], [0, -10])

  return (
    <Stage background={color.panel}>
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background:
            'radial-gradient(1200px 620px at 22% 18%, rgba(94,129,172,0.30), transparent 62%),' +
            'radial-gradient(900px 520px at 82% 88%, rgba(136,192,208,0.16), transparent 60%)',
        }}
      />

      <div
        style={{
          position: 'absolute',
          left: size.gutter,
          top: '50%',
          transform: `translateY(calc(-50% + ${drift}px))`,
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 18,
            opacity: mark,
            transform: `translateY(${interpolate(mark, [0, 1], [18, 0])}px)`,
          }}
        >
          <div
            style={{
              fontFamily: font.mono,
              fontWeight: 700,
              fontSize: 26,
              letterSpacing: 1,
              color: color.panel,
              background: color.paper,
              padding: '10px 14px',
              borderRadius: 10,
            }}
          >
            8848
          </div>
          <div
            style={{
              fontSize: 26,
              letterSpacing: 5,
              textTransform: 'uppercase',
              fontWeight: 600,
              color: 'rgba(236,239,244,0.62)',
            }}
          >
            Lab
          </div>
        </div>

        <div
          style={{
            marginTop: 46,
            fontSize: type.hero,
            lineHeight: 1.05,
            fontWeight: 700,
            letterSpacing: -2.5,
            color: color.paper,
            opacity: line1,
            transform: `translateY(${interpolate(line1, [0, 1], [26, 0])}px)`,
          }}
        >
          Document editing that
        </div>
        <div
          style={{
            fontSize: type.hero,
            lineHeight: 1.05,
            fontWeight: 700,
            letterSpacing: -2.5,
            color: color.accentOnDark,
            opacity: line2,
            transform: `translateY(${interpolate(line2, [0, 1], [26, 0])}px)`,
          }}
        >
          actually edits the document.
        </div>

        <div
          style={{
            marginTop: 40,
            width: interpolate(rule, [0, 1], [0, 560]),
            height: 2,
            background: `linear-gradient(90deg, ${color.accentOnDark}, transparent)`,
          }}
        />

        <div
          style={{
            marginTop: 26,
            fontSize: type.body,
            color: 'rgba(236,239,244,0.66)',
            opacity: rule,
            maxWidth: 900,
          }}
        >
          A deterministic PDF engine, driven in plain English — running entirely on your
          own machine.
        </div>
      </div>

      <InternalTag onDark />
    </Stage>
  )
}
