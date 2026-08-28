# v0.78 fixed runtime wheel record

These files are runtime inputs for the Darwin arm64 / CPython 3.9 replacement
simulation snapshot. They were downloaded without installation from the Python
package index using `pip download --only-binary=:all: --no-deps` and are bound
again by the v0.78 build manifest and snapshot inventory.

| Distribution | Version | Wheel SHA-256 | License |
|---|---:|---|---|
| attrs | 26.1.0 | `c647aa4a12dfbad9333ca4e71fe62ddc36f4e63b2d260a37a8b83d2f043ac309` | MIT |
| jsonschema | 4.25.1 | `3fba0169e345c7175110351d456342c364814cfcf3b964ba4587f22915230a63` | MIT |
| jsonschema-specifications | 2025.9.1 | `98802fee3a11ee76ecaca44429fda8a41bff98b00a0f2838151b113f210cc6fe` | MIT |
| referencing | 0.36.2 | `e8699adbbf8b5c7de96d8ffa0eb5c158b3beafce084968e2ea8bb08c6794dcd0` | MIT |
| rpds-py (cp39 macOS 11 arm64) | 0.27.1 | `1fea2b1a922c47c51fd07d656324531adc787e415c8b116530a1d29c0516c62d` | MIT |
| typing-extensions | 4.16.0 | `481caa481374e813c1b176ada14e97f1f67a4539ce9cfeb3f350d78d6370c2e8` | PSF-2.0 |

The `rpds/__init__.py` and native extension are exact extractions from the
recorded rpds wheel. Their SHA-256 values are respectively
`c373205d6ee5a530880b0d0a5dbc36d105f9ef7fe46ec12758878cb0202e82f3` and
`1eaf493c0e7c4a4634f671f58a4b05a0e079fcc61701c4bf583831dae908a7c1`.
Wheel `METADATA` declares the licenses above; license texts remain inside each
unaltered wheel. No vendored dependency has credentials, network configuration
or activation authority.
