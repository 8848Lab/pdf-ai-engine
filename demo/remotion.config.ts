import { Config } from '@remotion/cli/config'

Config.setVideoImageFormat('jpeg')
Config.setOverwriteOutput(true)
// Captured screenshots are the content; a higher CRF would smear the small
// mono type in the terminal cards and the document body.
Config.setCrf(16)
