import React from 'react'
import { interpolate, staticFile, useCurrentFrame } from 'remotion'
import { color, font, size } from '../theme'
import { Caption, Eyebrow, InternalTag, Stage, useEnter } from '../components/primitives'

/**
 * Beat 5. Redaction is the headline, but the engine is a document editor:
 * a layout-preserving text replacement and a metadata scrub, both from real
 * runs.
 */

/** A tight crop of one line of the captured page, scaled up so it is legible. */
const LineCrop: React.FC<{
  src: string
  width: number
  /** Fractions of the source image. */
  top: number
  height: number
  left?: number
  zoom?: number
}> = ({ src, width, top, height, left = 0.09, zoom = 2.6 }) => {
  const ASPECT = 1586 / 1224
  const imgWidth = width * zoom
  const imgHeight = imgWidth * ASPECT
  return (
    <div
      style={{
        position: 'relative',
        width,
        height: imgHeight * height,
        overflow: 'hidden',
        borderRadius: 10,
        border: `1px solid ${color.line}`,
        background: color.white,
      }}
    >
      <img
        src={src}
        style={{
          position: 'absolute',
          width: imgWidth,
          left: -left * imgWidth,
          top: -top * imgHeight,
        }}
      />
    </div>
  )
}

export const BeyondScene: React.FC = () => {
  const frame = useCurrentFrame()
  const enter = useEnter(0, 150)
  const a = useEnter(24, 170)
  const b = useEnter(110, 170)

  // The "Next Appointment" line sits at ~50.6% down page-before.png.
  const LINE_TOP = 0.4955
  const LINE_H = 0.0235

  return (
    <Stage>
      <div style={{ position: 'absolute', left: size.gutter, top: 74, opacity: enter }}>
        <Eyebrow>Not only redaction</Eyebrow>
        <div
          style={{
            marginTop: 12,
            fontSize: 50,
            fontWeight: 700,
            letterSpacing: -1.4,
            lineHeight: 1.12,
            maxWidth: 1500,
          }}
        >
          It edits the document, and it cleans what you cannot see.
        </div>
      </div>

      {/* Layout-preserving replacement, cropped tight to the line that changed. */}
      <div
        style={{
          position: 'absolute',
          left: size.gutter,
          top: 270,
          width: 780,
          opacity: a,
          transform: `translateY(${interpolate(a, [0, 1], [22, 0])}px)`,
        }}
      >
        <div style={{ fontSize: 28, fontWeight: 700 }}>Replace text, keep the layout</div>
        <div style={{ fontSize: 21, color: color.muted, marginTop: 8, lineHeight: 1.45 }}>
          Re-typeset at the block's own position, font and size — not pasted over it.
        </div>

        {[
          { src: 'captures/page-before.png', tag: 'before', tone: color.danger },
          { src: 'captures/page-typo-fixed.png', tag: 'after', tone: color.ok },
        ].map((row) => (
          <div key={row.tag} style={{ marginTop: 22 }}>
            <div
              style={{
                fontFamily: font.mono,
                fontSize: 16,
                fontWeight: 700,
                textTransform: 'uppercase',
                letterSpacing: 1.4,
                color: row.tone,
                marginBottom: 8,
              }}
            >
              {row.tag}
            </div>
            <LineCrop src={staticFile(row.src)} width={720} top={LINE_TOP} height={LINE_H} />
          </div>
        ))}

        <div style={{ marginTop: 18, fontSize: 20, color: color.muted, fontFamily: font.mono }}>
          Aprill → April
        </div>
      </div>

      {/* Metadata sanitize: the real panel, before and after. */}
      <div
        style={{
          position: 'absolute',
          right: size.gutter,
          top: 270,
          width: 800,
          opacity: b,
          transform: `translateY(${interpolate(b, [0, 1], [22, 0])}px)`,
        }}
      >
        <div style={{ fontSize: 28, fontWeight: 700 }}>Strip what travels invisibly</div>
        <div style={{ fontSize: 21, color: color.muted, marginTop: 8, lineHeight: 1.45 }}>
          Author, title, timestamps, the XMP stream, hidden text, embedded scripts.
        </div>

        {[
          { src: 'captures/metadata-before.png', tag: 'before', tone: color.danger },
          { src: 'captures/metadata-after.png', tag: 'after', tone: color.ok },
        ].map((row) => (
          <div key={row.tag} style={{ marginTop: 22 }}>
            <div
              style={{
                fontFamily: font.mono,
                fontSize: 16,
                fontWeight: 700,
                textTransform: 'uppercase',
                letterSpacing: 1.4,
                color: row.tone,
                marginBottom: 8,
              }}
            >
              {row.tag}
            </div>
            <img
              src={staticFile(row.src)}
              style={{
                width: '100%',
                display: 'block',
                borderRadius: 10,
                border: `1px solid ${color.line}`,
              }}
            />
          </div>
        ))}
      </div>

      <Caption delay={150}>
        Every operation is validated before it touches the file — and refuses rather than
        producing something that looks right and isn't.
      </Caption>
      <InternalTag />
    </Stage>
  )
}
