// SVGO config used by scripts/06_optimise_flags.py (spec §6.7).
//
// Conservative settings: strip metadata/title/desc/editor cruft, collapse
// groups, but preserve IDs (some flags use <use> references), and at
// least 3 decimal places of path precision (some flags carry fine
// geometric detail that drops out at lower precision).
//
// `prefixIds` namespaces every id, in-document reference and CSS class
// name with the flag's code (`ARG-rays`, `url(#BRA-B)`, `.AFG-fil3`).
// Commons files overwhelmingly use generic ids — `a`, `b`, `Layer_1` —
// so inlining several as <symbol>s per §9 would otherwise collide, and
// a `url(#a)` would resolve to whichever flag was inlined first.
// Prefixing rewrites definitions and references together, which is why
// `cleanupIds` can stay off without the ids being a hazard.
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
    {
      name: "prefixIds",
      params: {
        delim: "-",
        // The code, taken from the filename SVGO was handed: flags/ARG.svg
        // -> "ARG". SVGO's default prefix would keep the extension.
        prefix: (_node, info) => {
          const file = (info && info.path) || "";
          const base = file.split(/[/\\]/).pop() || "";
          return base.replace(/\.svg$/i, "") || "flag";
        },
      },
    },
    "removeTitle",
    "removeDesc",
    "removeMetadata",
    "removeEditorsNSData",
  ],
};
