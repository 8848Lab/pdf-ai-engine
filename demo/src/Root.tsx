import React from 'react'
import { Composition, registerRoot } from 'remotion'
import { Film } from './Film'
import { FPS, TOTAL_FRAMES, size } from './theme'

const RemotionRoot: React.FC = () => (
  <>
    <Composition
      id="Film"
      component={Film}
      durationInFrames={TOTAL_FRAMES}
      fps={FPS}
      width={size.width}
      height={size.height}
    />
  </>
)

registerRoot(RemotionRoot)
