#!/usr/bin/env bash
#
# release.sh — build and publish afferent to PyPI (or TestPyPI).
#
# Usage:
#   scripts/release.sh [--test] [--skip-tests] [--tag] [--yes]
#
#   --test         Upload to TestPyPI instead of PyPI.
#   --skip-tests   Skip the offline test run (NOT recommended).
#   --tag          After a successful real upload, create + push git tag vX.Y.Z.
#   --yes          Don't prompt before uploading.
#
# Auth (twine resolves in this order):
#   1. Env vars:   TWINE_USERNAME=__token__  TWINE_PASSWORD=pypi-AgE...   (recommended)
#      TestPyPI:   set the token from https://test.pypi.org/manage/account/token/
#   2. ~/.pypirc   ([pypi] / [testpypi] sections with username=__token__, password=<token>)
#   3. Interactive prompt.
#
#   Tokens: https://pypi.org/manage/account/token/  (scope to this project after first upload)
#
# Prefer the GitHub Actions workflow (.github/workflows/publish.yml) for
# routine releases — it uses PyPI Trusted Publishing and needs no token.
#
set -euo pipefail

cd "$(dirname "$0")/.."   # repo root

TEST=0; SKIP_TESTS=0; DO_TAG=0; ASSUME_YES=0
for arg in "$@"; do
  case "$arg" in
    --test)       TEST=1 ;;
    --skip-tests) SKIP_TESTS=1 ;;
    --tag)        DO_TAG=1 ;;
    --yes|-y)     ASSUME_YES=1 ;;
    -h|--help)    sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "unknown arg: $arg" >&2; exit 2 ;;
  esac
done

say() { printf '\n\033[1m▶ %s\033[0m\n' "$*"; }

# A venv is strongly recommended (system Python may be externally managed).
if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  echo "WARNING: not in a virtualenv. 'pip install' may fail on managed Pythons." >&2
  echo "         Consider: python3 -m venv .venv && source .venv/bin/activate" >&2
fi

say "Installing build tooling (build, twine)"
python3 -m pip install --quiet --upgrade build twine

if [[ "$SKIP_TESTS" -eq 0 ]]; then
  say "Running offline test suite"
  python3 -m unittest discover -s tests -p 'test_*.py' -t .
fi

VERSION="$(python3 -c 'import afferent; print(afferent.__version__)')"
say "Version: $VERSION"

if [[ -n "$(git status --porcelain)" ]]; then
  echo "WARNING: working tree is not clean. Commit before releasing for a clean tag." >&2
fi

say "Cleaning previous build artifacts"
rm -rf dist build ./*.egg-info 2>/dev/null || true

say "Building sdist + wheel"
python3 -m build

say "Validating artifacts (twine check)"
python3 -m twine check dist/*

TARGET="PyPI"; REPO_ARGS=()
if [[ "$TEST" -eq 1 ]]; then
  TARGET="TestPyPI"; REPO_ARGS=(--repository testpypi)
fi

if [[ "$ASSUME_YES" -eq 0 ]]; then
  printf '\nUpload afferent %s to %s? [y/N] ' "$VERSION" "$TARGET"
  read -r ans
  [[ "$ans" == "y" || "$ans" == "Y" ]] || { echo "aborted."; exit 1; }
fi

say "Uploading to $TARGET"
python3 -m twine upload "${REPO_ARGS[@]}" dist/*

say "Done — $TARGET has afferent $VERSION"
if [[ "$TEST" -eq 1 ]]; then
  echo "Verify:  pip install --index-url https://test.pypi.org/simple/ afferent==$VERSION"
else
  echo "Verify:  pip install afferent==$VERSION"
fi

if [[ "$DO_TAG" -eq 1 && "$TEST" -eq 0 ]]; then
  say "Tagging v$VERSION"
  git tag -a "v$VERSION" -m "afferent $VERSION"
  git push origin "v$VERSION"
fi
