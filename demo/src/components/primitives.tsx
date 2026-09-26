import React from 'react'
import { interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion'
import { color, font, size, type } from '../theme'

/**
 * Shared motion helpers. Everything eases from the same two curves so the
 * film feels like one piece rather than a pile of effects.
 */

export const useEnter = (delay = 0, damping = 200) => {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  return spring({ frame: frame - delay, fps, config: { damping }, durationInFrames: 28 })
}

/** Fade in, hold, fade out -- scoped to a sequence's own local frame. */
export const useHold = (durationInFrames: number, fadeIn = 12, fadeOut = 14) => {
  const frame = useCurrentFrame()
  return interpolate(
    frame,
    [0, fadeIn, durationInFrames - fadeOut, durationInFrames],
    [0, 1, 1, 0],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }
  )
}

export const Stage: React.FC<{
  children: React.ReactNode
  background?: string
  style?: React.CSSProperties
}> = ({ children, background = color.paper, style }) => (
  <div
    style={{
      position: 'absolute',
      inset: 0,
      background,
      fontFamily: font.sans,
      color: color.ink,
      overflow: 'hidden',
      ...style,
    }}
  >
    {children}
  </div>
)

/**
 * The persistent internal marking. Deliberately quiet: honest about what
 * this artifact is without undercutting the work it is showing.
 */
export const InternalTag: React.FC<{ onDark?: boolean }> = ({ onDark }) => (
  <div
    style={{
      position: 'absolute',
      bottom: 38,
      right: size.gutter,
      display: 'flex',
      alignItems: 'center',
      gap: 10,
      fontSize: 15,
      letterSpacing: 1.6,
      textTransform: 'uppercase',
      fontWeight: 600,
      color: onDark ? 'rgba(236,239,244,0.38)' : 'rgba(76,86,106,0.45)',
    }}
  >
    <span
      style={{
        width: 6,
        height: 6,
        borderRadius: 3,
        background: onDark ? 'rgba(236,239,244,0.38)' : 'rgba(76,86,106,0.45)',
      }}
    />
    Internal — not for distribution
  </div>
)

export const Eyebrow: React.FC<{ children: React.ReactNode; onDark?: boolean }> = ({
  children,
  onDark,
}) => (
  <div
    style={{
      fontSize: type.label,
      letterSpacing: 3,
      textTransform: 'uppercase',
      fontWeight: 700,
      color: onDark ? color.accentOnDark : color.accent,
    }}
  >
    {children}
  </div>
)

/**
 * The caption band. One line of plain language per beat, bottom-left, so
 * the film reads with the sound off -- which is how it will be watched.
 */
export const Caption: React.FC<{
  children: React.ReactNode
  delay?: number
  onDark?: boolean
}> = ({ children, delay = 0, onDark }) => {
  const enter = useEnter(delay)
  return (
    <div
      style={{
        position: 'absolute',
        left: size.gutter,
        bottom: 34,
        maxWidth: 1180,
        fontSize: type.caption,
        lineHeight: 1.45,
        fontWeight: 500,
        color: onDark ? 'rgba(236,239,244,0.82)' : color.muted,
        opacity: enter,
        transform: `translateY(${interpolate(enter, [0, 1], [14, 0])}px)`,
      }}
    >
      {children}
    </div>
  )
}

/** A captured screenshot, presented on restrained chrome so it reads as a real screen. */
export const Screen: React.FC<{
  src: string
  width: number
  /** Crop the source vertically: [topFraction, bottomFraction]. */
  crop?: [number, number]
  style?: React.CSSProperties
  aspect?: number
}> = ({ src, width, crop, style, aspect = 0.62 }) => {
  const height = width * aspect
  const inner = crop ? (
    <div style={{ position: 'absolute', inset: 0, overflow: 'hidden' }}>
      <img
        src={src}
        style={{
          position: 'absolute',
          width: '100%',
          top: `${-crop[0] * 100}%`,
          height: `${(1 / (crop[1] - crop[0])) * 100}%`,
          objectFit: 'cover',
          objectPosition: 'top',
        }}
      />
    </div>
  ) : (
    <img src={src} style={{ width: '100%', display: 'block' }} />
  )

  return (
    <div
      style={{
        width,
        height: crop ? height : undefined,
        position: 'relative',
        borderRadius: 14,
        overflow: 'hidden',
        background: color.white,
        border: `1px solid ${color.line}`,
        boxShadow: '0 30px 70px rgba(46,52,64,0.18), 0 4px 14px rgba(46,52,64,0.08)',
        ...style,
      }}
    >
      {inner}
    </div>
  )
}

/** A terminal-style block, matching the product's own terminal card. */
export const Terminal: React.FC<{
  title?: string
  children: React.ReactNode
  width?: number
  style?: React.CSSProperties
}> = ({ title = 'proof', children, width = 900, style }) => (
  <div
    style={{
      width,
      background: color.panel,
      border: `1px solid ${color.panelBorder}`,
      borderRadius: 12,
      overflow: 'hidden',
      boxShadow: '0 30px 70px rgba(46,52,64,0.28)',
      ...style,
    }}
  >
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '14px 18px',
        background: color.panel2,
        borderBottom: `1px solid ${color.panelBorder}`,
      }}
    >
      {['#bf616a', '#ebcb8b', '#a3be8c'].map((c) => (
        <span key={c} style={{ width: 11, height: 11, borderRadius: 6, background: c }} />
      ))}
      <span
        style={{
          marginLeft: 8,
          fontFamily: font.mono,
          fontSize: 17,
          color: 'rgba(236,239,244,0.55)',
        }}
      >
        {title}
      </span>
    </div>
    <div style={{ padding: '20px 24px', fontFamily: font.mono, fontSize: type.mono, lineHeight: 1.7 }}>
      {children}
    </div>
  </div>
)

/** Types a string out over frames -- used only where the product really typed. */
export const useTypedText = (text: string, startFrame: number, charsPerFrame = 1.6) => {
  const frame = useCurrentFrame()
  const shown = Math.max(0, Math.floor((frame - startFrame) * charsPerFrame))
  return text.slice(0, Math.min(shown, text.length))
}
