# Getting started — one-command Ubuntu setup

**The easiest way to use the entire quantitative research portfolio.**

You do **not** need Redis, Docker, a database, a globally installed Python
package, Dhan credentials, Streamlit on Vercel, or a paid backend to view the
public-facing research website. The Vite website is a static React application.

## Already cloned? Run ONE command

Open an Ubuntu terminal in the project:

```bash
cd ~/Desktop/codes/nifty50-momentum-backtest
git switch research/multi-factor-equity-index
git pull --ff-only origin research/multi-factor-equity-index
bash run.sh
```

The final command **does everything needed for the public website**:
checks Ubuntu system tools, installs any missing curl/git/xz prerequisites
using `apt` (may prompt once for sudo), selects an appropriate Node.js
runtime, installs JavaScript dependencies when needed, checks TypeScript and
the production Vite build, and then starts the site locally.

**Website:** http://127.0.0.1:5173

Leave the terminal open while using the website. Press **Ctrl+C** to stop it.
Future launches only need:

```bash
cd ~/Desktop/codes/nifty50-momentum-backtest && bash run.sh
```

No Dhan token is required to browse the educational mathematical explainers.
No market performance is fabricated.

## First time — no clone yet?

Install Git once if it is missing (`sudo apt install git`), then copy
this entire command block:

```bash
mkdir -p ~/Desktop/codes &&
cd ~/Desktop/codes &&
git clone --branch research/multi-factor-equity-index \
  https://github.com/5urabhi/nifty50-momentum-backtest.git &&
cd nifty50-momentum-backtest &&
bash run.sh
```

A private GitHub repository may ask you to authenticate with a configured
Git credential helper. The installer does not request credentials.

## Choose what to start

```bash
bash run.sh             # Default: lightweight React/Vite website only
bash run.sh research    # Local Python/Streamlit research laboratory
bash run.sh both        # Both website and Streamlit research laboratory
bash run.sh check       # Full Python unit tests, math acceptance and web build
bash run.sh setup       # Install everything and build; start no servers
bash run.sh --help      # Show usage and options
```

| Command | Starts | Typical address | Installs Python packages? |
| --- | --- | --- | --- |
| `bash run.sh` | React/Vite | http://127.0.0.1:5173 | No |
| `bash run.sh research` | Streamlit | http://127.0.0.1:8501 | Yes, isolated in `.venv` |
| `bash run.sh both` | Both | :5173 and :8501 | Yes |
| `bash run.sh check` | No server, verifies code | Test logs in terminal | Yes |
| `bash run.sh setup` | No server, prepares environment | N/A | Yes |

The website uses npm/Node only; running it does not require the Python engine.
The research laboratory uses Python and its own dependencies. No Redis service
or persistent background daemon is required. No GitHub Actions are created.

## What the installer checks

- Ubuntu/Debian `apt-get` (the automated path currently targets these OSes).
- Missing Git, curl, CA certificates and xz utilities.
- Node.js/npm version. A compatible system Node is used if present.
  Otherwise a **fixed Node.js v22.16.0 LTS Linux binary** is downloaded
  directly from nodejs.org and verified against its published SHA-256 list.
  It is installed inside ignored `.local-tools/`, not globally or via
  `curl | bash`. Downloads need internet access.
- `npm install` or `npm ci` if a package lock exists, with reinstall
  skipping when dependencies and package metadata have not changed.
- A TypeScript check and `npm run build` **before** opening Vite.
- For Python modes only: system Python 3.11+, `python3-venv`,
  an isolated `.venv`, and `requirements.txt` dependencies.
- In Python modes only: an ignored `.env` template is created if absent.

**Security:** the launcher does not print or transmit API tokens, doesn't
install Docker/Redis, and will not upgrade the entire operating system.
It only uses sudo when missing OS packages must be installed. Vite and
Streamlit bind to loopback (127.0.0.1) rather than exposing them to LAN.

If the build or tests fail, the command exits **with an error** instead of
pretending everything worked. Copy the terminal error output (redact any
secrets) for debugging. An already configured `.env` is never overwritten.

## Dhan API — optional research data

For raw historical data collection, start Python setup, then edit the token:

```bash
bash run.sh setup
nano .env
```

The file should contain:

```dotenv
DHAN_ACCESS_TOKEN=REPLACE_WITH_YOUR_OWN_TOKEN
```

The Dhan adapter loads this local `.env` automatically. Do not commit it.
Read **[Dhan API Setup](docs/DHAN_API_SETUP.md)** for token generation,
Security ID search, candle downloads and data limitations. Access tokens
expire; update `.env` with a fresh one as necessary.

Then retrieve current instrument information:

```bash
./.venv/bin/python scripts/dhan_data.py instrument-master
./.venv/bin/python scripts/dhan_data.py instrument-search --query "RELIANCE"
```

Use the reviewed Security IDs to configure real data downloads.
The public React website never accesses this token or Dhan directly.

## Animated explainers and recording a video

The website already includes a five-chapter story: research hypothesis,
cross-sectional factor signals, concentration constraints, three-asset
risk geometry and genuine holdout methodology. Select **Play story** to
advance automatically; rotate the 3D graph and move factor/cap sliders.

You can record the website locally using OBS Studio, optionally add
voiceover/subtitles, and feature the video at the top of the GitHub README.
**No MP4 is generated automatically.** See
[Showcase and Video Guide](docs/SHOWCASE_AND_VIDEO.md).

## Testing, build and deployment

**Python numerical and integration tests:**

```bash
bash run.sh check
```

**Production web build only, without starting a server:**

```bash
bash run.sh setup
```

The built static site is in `dist/`. Vercel can build it directly using
`npm run build` and `dist/`; it does **not** run Redis, Streamlit or the
Python research engine in production. The development PR remains draft.
Actual preview deployment must be tested independently.

**Real historical backtests require separate** point-in-time constituent
histories, corporate actions, publication-dated fundamentals, a compatible
TRI benchmark and source-rights review. The website cannot manufacture them.

## Troubleshooting

| Message | Resolution |
| --- | --- |
| `bash: run.sh: No such file` | Run `git pull --ff-only origin research/multi-factor-equity-index` from the correct project folder |
| `npm: command not found` | Use `bash run.sh` rather than running npm directly; it will install a verified local Node runtime |
| `pip/pandas: ModuleNotFoundError` | Use `bash run.sh research` or `./.venv/bin/python` (not system `python3`) |
| Port 5173 already used | Stop the earlier Vite session with Ctrl+C |
| Port 8501 already used | Stop the earlier Streamlit session |
| Frontend TypeScript error | The launcher stops before serving; share the compiler output |
| Cannot contact Node official download | Check HTTPS access to nodejs.org; retry later or install a compatible Node LTS manually |
| Dhan token missing or expired | `nano .env`, set a valid current DhanHQ access token |
| No historical return plots | Expected until real-market research data are separately approved and exported |
| Snap Store unavailable | Snap is not required; Ubuntu apt + verified Node downloads are sufficient |

**Scope:** Ubuntu/Debian local-first installation. macOS/Windows users can
install Python 3.11+, Node LTS and dependencies manually according to
the existing [local runbook](docs/LOCAL_RUN.md).
