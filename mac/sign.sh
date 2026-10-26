#!/bin/zsh
# Sign an app with a stable, self-signed certificate: macOS ties folder permissions to the app's
# signature, so an ad-hoc signature (different on every build) makes it ask again after each update.
# The certificate lives in its own keychain, ~/Library/Keychains/semsearch-signing.keychain-db, with a
# random password kept in ~/.semsearch/signing-keychain.pw. Falls back to an ad-hoc signature.
# Usage: mac/sign.sh /path/to/App.app
set -uo pipefail
APP="$1"
NAME="SemSearch Local Signing"
KC="$HOME/Library/Keychains/semsearch-signing.keychain-db"
PWFILE="$HOME/.semsearch/signing-keychain.pw"

ensure_identity() {
  if [[ -f "$KC" && -f "$PWFILE" ]]; then
    security unlock-keychain -p "$(cat "$PWFILE")" "$KC" 2>/dev/null && return 0
  fi
  # (re)create: a missing password or an unusable keychain starts over
  rm -f "$KC"
  local tmp pw
  tmp="$(mktemp -d)"
  pw="$(/usr/bin/openssl rand -hex 16)"
  mkdir -p "$(dirname "$PWFILE")"
  (umask 077; print -r -- "$pw" > "$PWFILE")
  /usr/bin/openssl req -x509 -newkey rsa:2048 -nodes -days 7300 -subj "/CN=$NAME" \
    -keyout "$tmp/key.pem" -out "$tmp/cert.pem" \
    -addext "keyUsage=critical,digitalSignature" -addext "extendedKeyUsage=critical,codeSigning" \
    -addext "basicConstraints=critical,CA:false" 2>/dev/null &&
  /usr/bin/openssl pkcs12 -export -inkey "$tmp/key.pem" -in "$tmp/cert.pem" -name "$NAME" \
    -out "$tmp/id.p12" -passout "pass:$pw" 2>/dev/null &&
  security create-keychain -p "$pw" "$KC" &&
  security set-keychain-settings "$KC" &&
  security unlock-keychain -p "$pw" "$KC" &&
  security import "$tmp/id.p12" -k "$KC" -P "$pw" -T /usr/bin/codesign >/dev/null &&
  security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "$pw" "$KC" >/dev/null
  local ok=$?
  rm -rf "$tmp"
  return $ok
}

sign_stable() {
  # codesign only finds identities on the keychain search list: add ours for the signing, then restore
  local -a orig
  orig=("${(@f)$(security list-keychains -d user | sed -e 's/^ *"//' -e 's/"$//')}")
  orig=("${(@)orig:#}")  # drop empty lines
  (( ${#orig} )) || return 1  # never replace a search list we could not read
  security list-keychains -d user -s "${orig[@]}" "$KC" || return 1
  codesign --force --sign "$NAME" "$APP"
  local ok=$?
  security list-keychains -d user -s "${orig[@]}"
  return $ok
}

if ensure_identity && sign_stable; then
  exit 0
fi
echo "Note: could not sign with a stable certificate; using an ad-hoc signature (macOS may ask for folder access again after updates)."
codesign --force --sign - "$APP"
