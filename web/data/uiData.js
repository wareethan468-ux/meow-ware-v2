/**
 * Seed data — shown only in browser preview mode (no pywebview).
 * When the desktop app is running, flags come from the Python backend
 * via get_user_flags(), so seedFlags is empty.
 */
export const seedFlags = [];

export const presetGroups = [
  {
    name: 'Resolution (DFIntDebugDynamicRenderKiloPixels)',
    flag: 'DFIntDebugDynamicRenderKiloPixels',
    options: [
      ['720p (921)', '921'],
      ['1080p (2074)', '2074'],
      ['1440p (3686)', '3686'],
    ],
    defaultValue: '2074',
    description: 'Sets DFIntDebugDynamicRenderKiloPixels',
  },
  {
    name: 'Render Distance (FIntCameraFarZPlane)',
    flag: 'FIntCameraFarZPlane',
    options: [
      ['Low (250)', '250'],
      ['Good (500)', '500'],
      ['Far (1000)', '1000'],
    ],
    defaultValue: '500',
    description: 'Sets FIntCameraFarZPlane',
  },
  {
    name: 'Sharpness (MSAA Samples)',
    flag: 'FIntDebugForceMSAASamples',
    relatedFlags: ['FIntDebugFRMOptionalMSAALevelOverride'],
    options: [
      ['Soft (1)', '1'],
      ['Balanced (2)', '2'],
      ['Sharp (4)', '4'],
      ['Ultra (8)', '8'],
    ],
    defaultValue: '4',
    description:
      'Sets FIntDebugForceMSAASamples & FIntDebugFRMOptionalMSAALevelOverride',
  },
];

export const previewLogs = [
  '[6:05:07 PM] Vellium Tweaker v2.3.0 (multi-process)',
  '[6:05:08 PM] Fetching fflags offsets from https://offsets.imtheo.lol/fflags.hpp...',
  '[6:05:08 PM] Fetching external offsets from https://offsets.imtheo.lol/offsets.hpp...',
  '[6:05:08 PM] Saved 14265 FastFlag offsets to cache',
  '[6:05:08 PM] Synced 14265 FastFlag offsets and 389 external offsets for version-f5a60436d48947d3',
  '[6:05:08 PM] New Roblox process detected (PID: 20748)',
  '[6:05:08 PM] Attached to PID 20748 (version-f5a60436d48947d3)',
  '[6:05:08 PM] Monitor is active - watching for flag changes every 5s',
];
