// SVGO config used by scripts/06_optimise_flags.py (spec §6.7).
//
// Conservative settings: strip metadata/title/desc/editor cruft, collapse
// groups, but preserve IDs (some flags use <use> references), and at
// least 3 decimal places of path precision (some flags carry fine
// geometric detail that drops out at lower precision).
//
// `removeViewBox` is not enabled by preset-default in modern SVGO, so we
// don't need to override it. viewBox is synthesised post-SVGO in the
// optimisation script for any flag that ships only with width/height.

export default {
  multipass: true,
  floatPrecision: 3,
  plugins: [
    {
      name: "preset-default",
      params: {
        overrides: {
          cleanupIds: false,
        },
      },
    },
    "removeTitle",
    "removeDesc",
    "removeMetadata",
    "removeEditorsNSData",
  ],
};
