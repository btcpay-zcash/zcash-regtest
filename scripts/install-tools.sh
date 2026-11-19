#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOOLS="$ROOT/tools"
ZKOOL_SOURCE="${ZKOOL_SOURCE:-$ROOT/../zkool2}"
cargo install --locked --git https://github.com/ZcashFoundation/zebra \
  --tag "${ZEBRA_VERSION:-v6.2.1}" --features=internal-miner --root "$TOOLS" zebrad
SOURCE_DIR="$(mktemp -d)"
trap 'rm -rf "$SOURCE_DIR"' EXIT
git clone https://github.com/zecrocks/lightwalletd.git "$SOURCE_DIR/lightwalletd"
git -C "$SOURCE_DIR/lightwalletd" checkout --detach "${LIGHTWALLETD_REVISION:-09593edbee4ee68d47e5a53f8ce1c83514c4e8e6}"
go build -C "$SOURCE_DIR/lightwalletd" -o "$TOOLS/bin/lightwalletd" .
# Build the wallet under test, including its workspace patches.
cargo build --manifest-path "$ZKOOL_SOURCE/Cargo.toml" --release --no-default-features --features graphql --bin zkool_graphql
cp "$ZKOOL_SOURCE/target/release/zkool_graphql" "$TOOLS/bin/zkool_graphql"
echo "Installed regtest tools in $TOOLS/bin"
