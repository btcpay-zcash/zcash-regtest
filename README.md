# Zcash regtest

Two modes are available: native processes for local development, and the existing
Docker Compose stack for cloud/container environments.

## Local mode (no Docker)

Requires Rust/Cargo, Go, Git, Python 3 and clang/libclang. On macOS install the
Xcode command-line tools and `brew install go llvm`; on Linux install clang and
libclang-dev with your package manager. The sibling `../zkool2` checkout supplies
the GraphQL wallet; override `ZKOOL_SOURCE` to use another checkout.

```sh
./scripts/install-tools.sh
./scripts/regtest.sh start
./scripts/regtest.sh status
./scripts/regtest.sh stop
```

The installer pins Zebra v6.2.1 (`internal-miner`) and lightwalletd revision
09593edbee4ee68d47e5a53f8ce1c83514c4e8e6, and builds the local zkool_graphql with
workspace patches. Tools are cached in `tools/bin`; the launcher also finds tools
on PATH. The first wallet start may download Sapling proving parameters.

`start` runs Zebra, lightwalletd, and the main/cashcow GraphQL servers in the
background and waits for readiness. The first start creates state under
`data/local/run-*`; subsequent starts resume the last managed run. Repeating
`start` or `stop` is safe. `stop` terminates only the tracked launcher, which stops
its own child processes, and preserves chain, wallet databases, keys and logs.
The controller checks both the PID and a unique ownership token before signalling.
`status` shows the managed run's readiness, endpoints, state directory and logs.

Ports are 18232 (Zebra RPC), 18233 (P2P), 8137 (lightwalletd), 18081 (main
`/graphql`) and 18082 (cashcow `/graphql`), all on loopback. Occupied ports fail
startup. New chains are mined to 300 blocks with NU6.3 activating at 250; resumed
chains keep their current height. Component logs and `launcher.log` are appended
inside the state directory.

To resume a particular run or deliberately create a fresh one:

```sh
./scripts/regtest.sh start --state-dir /absolute/path/to/data/local/run-...
# Stop first before selecting another run.
./scripts/regtest.sh stop
./scripts/regtest.sh start --fresh
```

The foreground launcher remains available as `scripts/run-local.py` (Ctrl-C stops
its children), with optional `--state-dir`. Foreground runs are separate from the
controller's managed run; use the controller for background start/stop operations.

For BTCPay, start `scripts/run-local.sh` from the sibling plugin repository once.
It detects the running GraphQL servers and supplies the matching miner seed;
BTCPay's existing cheatmode creates/funds cashcow account 1 and miner account 2.
Then generate the receiving wallet:

```sh
./scripts/prepare-test-wallet.py
```

This creates a separate account in the cashcow instance and exports its generated
seed and unified full viewing key to ignored `data/local/current.env` with mode
0600. It reuses that receiving account on later manual runs. `--new` generates a fresh
receiver; the browser runner uses this automatically to prevent earlier test
deposits from being credited to a new invoice. Each receiver is also saved in
`data/local/receiver-<account-id>.env`. Main-wallet imports should
use `BTCPAY_TEST_VIEWING_KEY` from this file; the spending seed stays in cashcow.
Only the fixed public miner seed remains a hardcoded fixture.

Run `scripts/test-playwright.sh` from the plugin repository to exercise checkout.
The runner loads the local env file and imports the viewing key through BTCPay's
wallet settings. Set `BTCPAY_TEST_WALLET=regtest` to require real services or `mock`
to force the mock; the default detects the server and falls back when unavailable.
Use `scripts/verify-local.py` for read-only checks of funding, the watch-only
receiver, and the server-side notes filter after a successful payment test.
HTTP tests continue using isolated mocks. Run browser tests against the shared
chain serially. APIs bind to loopback without authentication for development.

## Docker mode

The existing `docker-compose.yml`, `.env.example`, `misc/` configurations and
`mine.sh` remain available:

```sh
cp .env.example .env
# Configure the miner address and chain settings in misc/zebra.toml.
docker compose up --build -d
```

Compose starts Zebra and lightwalletd. Run/configure the GraphQL wallet separately
and use `mine.sh` for manual funding as before. Its chain activation heights must
match the wallet build used; the native launcher generates its own configuration
and does not change the Docker configuration.
