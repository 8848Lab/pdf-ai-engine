import React from 'react'
import { interpolate, useCurrentFrame } from 'remotion'
import { color, font, size, type } from '../theme'
import { InternalTag, Stage, useEnter } from '../components/primitives'

const CAPABILITIES = [
  'Redact — content removed, not covered',
  'Replace text — layout and font preserved',
  'Delete, move, insert blocks',
  'Replace images, one placement at a time',
  'Sanitize metadata, XMP, hidden text, scripts',
  'Driven in plain English, or called directly',
]

export const Close: React.FC = () => {
  const frame = useCurrentFrame()
  const enter = useEnter(0, 150)
  const rule = useEnter(16, 190)
  const tail = useEnter(130, 170)
  const drift = interpolate(frame, [0, 300], [0, -8])

  return (
    <Stage background={color.panel}>
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background:
            'radial-gradient(1000px 560px at 78% 22%, rgba(94,129,172,0.28), transparent 62%),' +
            'radial-gradient(820px 460px at 14% 84%, rgba(136,192,208,0.14), transparent 60%)',
        }}
      />

      <div
        style={{
          position: 'absolute',
          left: size.gutter,
          top: '50%',
          transform: `translateY(calc(-50% + ${drift}px))`,
          opacity: enter,
        }}
      >
        <div
          style={{
            fontSize: 56,
            fontWeight: 700,
            letterSpacing: -1.8,
            color: color.paper,
            lineHeight: 1.1,
            maxWidth: 900,
          }}
        >
          One engine. Every operation deterministic.
        </div>

        <div
          style={{
            marginTop: 30,
            width: interpolate(rule, [0, 1], [0, 460]),
            height: 2,
            background: `linear-gradient(90deg, ${color.accentOnDark}, transparent)`,
          }}
        />

        <div style={{ marginTop: 34, display: 'grid', gap: 14 }}>
          {CAPABILITIES.map((c, i) => {
            const item = interpolate(frame, [26 + i * 9, 44 + i * 9], [0, 1], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
            })
            return (
              <div
                key={c}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 16,
                  opacity: item,
                  transform: `translateX(${interpolate(item, [0, 1], [-16, 0])}px)`,
                }}
              >
                <span
                  style={{
                    width: 7,
                    height: 7,
                    borderRadius: 4,
                    background: color.accentOnDark,
                    flexShrink: 0,
                  }}
                />
                <span style={{ fontSize: 27, color: 'rgba(236,239,244,0.86)' }}>{c}</span>
              </div>
            )
          })}
        </div>
      </div>

      <div
        style={{
          position: 'absolute',
          right: size.gutter,
          bottom: 130,
          textAlign: 'right',
          opacity: tail,
        }}
      >
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 16,
          }}
        >
          <div
            style={{
              fontFamily: font.mono,
              fontWeight: 700,
              fontSize: 26,
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
            marginTop: 16,
            fontSize: 21,
            color: 'rgba(236,239,244,0.46)',
          }}
        >
          Runs offline. Your documents stay yours.
        </div>
      </div>

      <InternalTag onDark />
    </Stage>
  )
}
