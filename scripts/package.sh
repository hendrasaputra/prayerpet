#!/bin/bash
# Build dist/prayerpet-<version>.tar.gz for copying to the Pi.
# Checks that the version in prayerpet/__init__.py and install.sh agree, and that tests pass.
#   bash scripts/package.sh            # test + build
#   bash scripts/package.sh --no-test  # build only
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' prayerpet/__init__.py)
INSTALLER=$(sed -n 's/^echo "Prayer Pet installer v\(.*\)"/\1/p' install.sh)
if [ -z "$VERSION" ] || [ "$VERSION" != "$INSTALLER" ]; then
  echo "Version mismatch: prayerpet/__init__.py=$VERSION install.sh=$INSTALLER"; exit 1
fi

if [ "${1:-}" != "--no-test" ]; then
  python3 -m unittest discover -s tests -t . -q
  bash tests/test_wifi_fallback.sh
fi

# Never ship secrets or private data
if grep -rIlE 'token = "[0-9]+:[A-Za-z0-9_-]{20,}"|AIza[0-9A-Za-z_-]{20,}' prayerpet tools install.sh prayerpet.toml README.md; then
  echo "Refusing to package: a real token or API key appears in the files above."; exit 1
fi

mkdir -p dist
STAGE="$(mktemp -d)"
mkdir -p "${STAGE:?}/prayerpet"
cp -r prayerpet tools install.sh prayerpet.toml README.md "${STAGE:?}/prayerpet/"
find "${STAGE:?}" -name __pycache__ -prune -exec rm -rf {} +
COPYFILE_DISABLE=1 tar --no-xattrs -czf "dist/prayerpet-${VERSION}.tar.gz" -C "${STAGE:?}" prayerpet
rm -rf "${STAGE:?}"
echo "Built dist/prayerpet-${VERSION}.tar.gz"
echo "Deploy:  scp dist/prayerpet-${VERSION}.tar.gz <user>@<pi-host>:~"
echo "On Pi:   cd ~ && tar xzf prayerpet-${VERSION}.tar.gz && cd prayerpet && bash install.sh"
