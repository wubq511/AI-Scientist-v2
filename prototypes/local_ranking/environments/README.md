# Local-ranking reference environments

`requirements.in` is the approved direct dependency snapshot for the local-ranking comparison. Platform locks are generated with `uv 0.12.4`, Python 3.13, PyPI binary distributions only, and no source builds. CPU FP32 is enforced by the harness at runtime; it is not inferred from a wheel name.

```bash
uv pip compile prototypes/local_ranking/environments/requirements.in \
  --python-version 3.13 \
  --python-platform x86_64-pc-windows-msvc \
  --only-binary :all: \
  --generate-hashes \
  --output-file prototypes/local_ranking/environments/requirements.windows-x86_64-py313.txt

uv pip compile prototypes/local_ranking/environments/requirements.in \
  --python 3.13.7 \
  --only-binary :all: \
  --generate-hashes \
  --output-file prototypes/local_ranking/environments/requirements.macos-arm64-py313.txt
```

Formal environments must install from the matching lock with hash checking and without source builds. A lock proves resolution identity, not that an environment has passed the protocol's offline, import, model, latency, memory, or payload-determinism gates.

The macOS lock is resolved against the actual reference host because `torch 2.13.0` requires a `macosx_14_0_arm64` wheel, while `uv --python-platform aarch64-apple-darwin` currently models a macOS 13 deployment target and correctly rejects that wheel. The Windows lock is cross-resolved for `win_amd64`. The failed uniform `--torch-backend cpu` resolution is retained in the session evidence; that index exposes a Windows `2.13.0+cpu` build but no corresponding macOS local-version build.
