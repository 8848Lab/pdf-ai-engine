import React from 'react'
import { interpolate } from 'remotion'
import { color, font } from '../theme'
import { useEnter } from './primitives'

/**
 * An annotation drawn over a captured screenshot, positioned in the
 * SOURCE IMAGE's own fractional coordinate space. Because the image is
 * placed with a known box, fractions survive any scaling of that box --
 * so a callout keeps pointing at the same pixels if the layout is retimed
 * or resized, rather than drifting off its target.
 */
export type Box = {
  /** All four are fractions of the source image, 0..1. */
  x: number
  y: number
  w: number
  h: number
}

export const Highlight: React.FC<{
  box: Box
  label?: string
  delay?: number
  tone?: 'danger' | 'accent' | 'ok'
  /** Which side the label sits on. */
  side?: 'right' | 'left'
}> = ({ box, label, delay = 0, tone = 'danger', side = 'right' }) => {
  const enter = useEnter(delay, 180)
  const stroke = tone === 'danger' ? color.danger : tone === 'ok' ? color.ok : color.accent

  return (
    <>
      <div
        style={{
          position: 'absolute',
          left: `${box.x * 100}%`,
          top: `${box.y * 100}%`,
          width: `${box.w * 100}%`,
          height: `${box.h * 100}%`,
          border: `2.5px solid ${stroke}`,
          borderRadius: 6,
          background: `${stroke}14`,
          opacity: enter,
          transform: `scale(${interpolate(enter, [0, 1], [1.06, 1])})`,
          transformOrigin: 'center',
          boxShadow: `0 0 0 6px ${stroke}10`,
        }}
      />
      {label ? (
        <div
          style={{
            position: 'absolute',
            top: `calc(${(box.y + box.h / 2) * 100}% - 17px)`,
            ...(side === 'right'
              ? { left: `calc(${(box.x + box.w) * 100}% + 18px)` }
              : { right: `calc(${(1 - box.x) * 100}% + 18px)` }),
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            opacity: enter,
            transform: `translateX(${interpolate(enter, [0, 1], [side === 'right' ? -12 : 12, 0])}px)`,
            whiteSpace: 'nowrap',
          }}
        >
          <span
            style={{
              width: 16,
              height: 2,
              background: stroke,
              opacity: 0.65,
              order: side === 'right' ? 0 : 1,
            }}
          />
          <span
            style={{
              fontFamily: font.mono,
              fontSize: 19,
              fontWeight: 600,
              color: stroke,
              background: color.white,
              border: `1px solid ${stroke}40`,
              padding: '5px 11px',
              borderRadius: 6,
            }}
          >
            {label}
          </span>
        </div>
      ) : null}
    </>
  )
}

/**
 * A screenshot with annotations anchored to it.
 *
 * Two things this gets right that a naive wrapper does not:
 *
 * 1. The IMAGE is clipped (rounded corners, optional crop) but the
 *    ANNOTATION LAYER is not. Clipping both truncates every label that sits
 *    outside the shot -- which is most of them.
 * 2. With a crop, the annotation layer is still sized and offset to the
 *    FULL image, so `Highlight` boxes stay expressed in the source image's
 *    own fractions. Callers never have to rescale coordinates by hand when
 *    a crop changes.
 */
export const AnnotatedShot: React.FC<{
  src: string
  width: number
  /** Source image aspect (height / width). Needed only when cropping. */
  aspect?: number
  /** Show only this vertical slice of the source: [top, bottom] fractions. */
  crop?: [number, number]
  children?: React.ReactNode
  style?: React.CSSProperties
}> = ({ src, width, aspect, crop, children, style }) => {
  const fullHeight = aspect ? width * aspect : undefined
  const [top, bottom] = crop ?? [0, 1]
  const displayHeight = fullHeight ? fullHeight * (bottom - top) : undefined
  const offset = fullHeight ? -top * fullHeight : 0

  return (
    <div
      style={{
        position: 'relative',
        width,
        height: displayHeight,
        overflow: 'visible',
        ...style,
      }}
    >
      <div
        style={{
          position: 'absolute',
          inset: 0,
          borderRadius: 12,
          overflow: 'hidden',
          background: color.white,
          border: `1px solid ${color.line}`,
          boxShadow: '0 28px 64px rgba(46,52,64,0.20), 0 3px 10px rgba(46,52,64,0.07)',
        }}
      >
        <img
          src={src}
          style={{
            position: 'absolute',
            width: '100%',
            top: offset,
            left: 0,
            display: 'block',
          }}
        />
      </div>

      <div
        style={{
          position: 'absolute',
          left: 0,
          top: offset,
          width: '100%',
          height: fullHeight,
          pointerEvents: 'none',
        }}
      >
        {children}
      </div>
    </div>
  )
}
