# Third-party notices for the FGS Renderer build

The renderer bundles these production dependencies, pinned in `pnpm-lock.yaml`:

| Package | Version | Declared license | Included notice |
| --- | --- | --- | --- |
| `pdf-lib` | 1.17.1 | MIT | `licenses/pdf-lib-MIT.txt` |
| `@pdf-lib/fontkit` | 1.1.1 | MIT | `licenses/fontkit-MIT.txt` |
| `@pdf-lib/standard-fonts` | 1.0.0 | MIT | `licenses/standard-fonts-MIT.txt` |
| `@pdf-lib/upng` | 1.0.1 | MIT | `licenses/upng-MIT.txt` |
| `pako` | 1.0.11 | MIT and Zlib | `licenses/pako-MIT.txt` |
| `tslib` | 1.14.1 | 0BSD | `licenses/tslib-0BSD.txt` |

The `@pdf-lib/fontkit` package metadata and [package README](https://github.com/Hopding/fontkit)
declare MIT, but the published package does not contain a separate LICENSE
file. Its included notice records that limitation and the package's listed
author and contributor.

The bundled Noto fonts have their own SIL Open Font License and copyright
notice in `fonts/OFL.txt`. The esbuild compiler is a development dependency;
it is not included in the browser or Node bundles.
