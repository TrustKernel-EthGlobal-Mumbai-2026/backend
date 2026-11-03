# Portable setup and commands

## Standard-library path

Use Python3.11. From repository root, run `python -B -m unittest discover -s procedural_loop/tests -v`, then `python -B tools/offline_demo.py --output .local-runs/demo-001`. The output directory must not exist. No dependency/network installation or model is involved. The new staging demo invokes preserved `run_one` logic and guards its packaged implementation/fixture files, instead of invoking the original full-corpus launcher that requires private historical/budget manifests. This changes the public entry point, not the frozen implementation.

Inspect one shape with `python -B -m procedural_loop.runner inspect --run .local-runs/demo-001/single --kind host.proposal.held`, or validate its JSONL/index with `python -B -m procedural_loop.runner validate --run .local-runs/demo-001/single`. All generated state is ignored by Git.

The new live-verification suite also runs offline with standard library: `python -B -m unittest discover -s live_verification/tests -v`. Its35tests construct temporary recorded-like corpus/mocks; they do not consume private originals. Together with66procedural tests this is101portable tests. Other historical suites need their documented environments/private prerequisites. Do not run broad historical build/test setup against preserved accepted profiles. A full original recorded/live corpus audit is not reproducible from a public-safe export that deliberately excludes those inputs. CI mirrors the two portable suites and uses `-S` to exclude installed site packages.

## Optional native dependency setup

These commands are documentation, not actions performed by repository preparation. Installing dependencies/cloning upstream uses the network and should be a deliberate local setup step:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.lock.txt
git clone https://github.com/TauricResearch/TradingAgents.git upstream/TradingAgents
git -C upstream/TradingAgents checkout --detach c4544913a14ed3df5f1ed7b9e8483270ce20682a
.venv\Scripts\python -m pip install --no-deps -e upstream/TradingAgents
```

For POSIX use `.venv/bin/python`. The lock file is the preserved recorded Windows environment, not a wheel/platform guarantee; other operating systems may need platform-specific resolution. Exact source pin and upstream license remain required. Native model names/access and provider services are historical configuration and may not remain available.

Do not copy a virtual environment, source-cache database, API key or cumulative budget database into Git. Do not auto-create a fresh budget to bypass the missing private spending context. Original paid launchers require their private safeguards and separate execution authorization. Setup does not launch models, source probes, accounts, signatures or trades. FRED/source/API credential names in code are configuration interfaces, not included credentials.

## Live verification private inputs

The November4 live-corpus ledger/rules lane completed and the parent authorized its frozen code/docs/tests for staging. Its actual run is live-verification-20261103T190006Z-85ac8aae, pinned ledger build live-ledger-15d9ba24f994cafddc16. The input six-arm live recording, full canonical/finding outputs and private protection snapshot are excluded. Restoring a reviewed private evidence pack is required before running the original data-backed CLI or its corpus-dependent tests. Do not replace missing originals with synthetic values, bootstrap a budget file or point at a mutable latest directory.
