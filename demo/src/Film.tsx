import React from 'react'
import { AbsoluteFill, Sequence } from 'remotion'
import { color, scenes } from './theme'
import { Title } from './scenes/Title'
import { DocumentScene } from './scenes/DocumentScene'
import { InstructionScene } from './scenes/InstructionScene'
import { ProofScene } from './scenes/ProofScene'
import { BeyondScene } from './scenes/BeyondScene'
import { Close } from './scenes/Close'

/**
 * The spine. Scene timings live in theme.ts so the whole film can be
 * retimed from one place; each Sequence is given a couple of frames of
 * overlap-free room rather than cross-fading, which keeps hard cuts crisp
 * on captured screenshots.
 */
export const Film: React.FC = () => (
  <AbsoluteFill style={{ background: color.paper }}>
    <Sequence from={scenes.title.from} durationInFrames={scenes.title.duration} name="Title">
      <Title />
    </Sequence>

    <Sequence
      from={scenes.document.from}
      durationInFrames={scenes.document.duration}
      name="Document"
    >
      <DocumentScene />
    </Sequence>

    <Sequence
      from={scenes.instruction.from}
      durationInFrames={scenes.instruction.duration}
      name="Instruction"
    >
      <InstructionScene />
    </Sequence>

    <Sequence from={scenes.proof.from} durationInFrames={scenes.proof.duration} name="Proof">
      <ProofScene />
    </Sequence>

    <Sequence from={scenes.beyond.from} durationInFrames={scenes.beyond.duration} name="Beyond">
      <BeyondScene />
    </Sequence>

    <Sequence from={scenes.close.from} durationInFrames={scenes.close.duration} name="Close">
      <Close />
    </Sequence>
  </AbsoluteFill>
)
