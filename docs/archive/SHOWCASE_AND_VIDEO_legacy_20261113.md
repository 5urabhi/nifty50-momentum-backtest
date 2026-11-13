# Public Research Website & Motion Explainer

## What is built

This repository now has two **separate presentations**:

- **React/Vite research story** at the repository root. A lightweight,
  public, static website with animated SVG charts, factor controls, portfolio
  weights, an interactive perspective projection of a three-asset covariance
  risk surface, and a five-chapter autoplay explainer. It can be deployed to
  Vercel without running Python or Streamlit on the server.
- **Python Streamlit laboratory** under `dashboard/`. It remains intact for
  private, local experiment configuration, numerical analysis and research
  validation. It is *not* needed to serve the Vercel website.

The public site can be used as the visual element of a 2–3 minute narrated
demonstration video. The full editable code remains in GitHub.

## Start the React website on Ubuntu

Clone the development branch if needed, or pull it into the existing clone:

```bash
cd ~/Desktop/codes/nifty50-momentum-backtest
git switch research/multi-factor-equity-index
git pull --ff-only origin research/multi-factor-equity-index

# Ubuntu: install supported Node.js (LTS 20.19+ or 22.12+) first if not installed.
node --version
npm --version

npm install
npm run dev
```

Open the Vite URL reported in your terminal (normally http://127.0.0.1:5173).

**Build/preview** locally:

```bash
npm run build
npm run preview
```

Only a successful `npm run build` and a manual browser inspection verify the
front-end. A completed source file does not establish that it visually works
on Firefox, Chromium and mobile.

## The explainer chapters

| Time in a 2–3 min reel/video | Scene | Interaction |
| --- | --- | --- |
| 0:00–0:20 | Hero: market noise and mathematical research | Animated equity curve |
| 0:20–0:45 | Research question | European call-price example |
| 0:45–1:10 | Five equity factors | Select factor to explain rationale |
| 1:10–1:35 | Index construction | Drag stock concentration cap |
| 1:35–2:00 | Covariance risk geometry | Rotate the 3D feasible portfolio surface |
| 2:00–2:20 | Holdout validation | Animated conceptual index vs benchmark |
| 2:20–2:45 | Models and evidence | Show code and documented release gates |

Click **Play story** to advance automatically through the five lessons,
or click the chapter dots manually. For actual recording, use OBS Studio
(Window Capture) and record at 1920x1080 or 1080x1920 as needed; keep
the chapter controls visible or crop them intentionally. Add your own
voiceover and captions to explain your modeling decisions.

We have **not** auto-generated or published a video file. There is no need
to download external imagery or third-party animation assets; this is
code-rendered mathematical animation. If you later want a programmatic MP4
renderer, add it after the final content and visual QA are frozen.

## Mathematical integrity of the presentation

- The hero graph and all default animated visuals are **conceptual or
  synthetic demonstrations**, *not* actual Nifty returns.
- Factor scores are illustrative; they are not computed from a user's
  brokerage account or from historical filings.
- The 3D portfolio surface is a mathematical perspective projection of
  a covariance-derived three-security volatility grid, not real portfolio
  forecasts.
- The option-pricing curve is a front-end illustrative Black–Scholes
  calculation. The verified numerical source of truth is the Python
  mathematical research engine.
- The **Research Evidence** panel has **no return claim by default**.
  Only a deliberately exported aggregate snapshot enables historical charts.

## Explicitly approve a research snapshot

**Only after independently reviewing its input source licenses, point-in-time
vintages, benchmark convention, holdout validation and privacy**:

```bash
python scripts/export_static_dashboard.py \
  --results-dir results/research_v1 \
  --publish
```

This writes `public/data/summary.json` and `public/data/returns.csv` for
the Vite website. You must manually inspect these before adding them to
Git or deploying. The exporter is deliberately opt-in.

**Do not publish** licensed constituent lists, account holdings, Dhan API
tokens, raw filing exports, or unpublished trading research.

## Deploying to Vercel later

The repository `vercel.json` now configures a **Vite build** with the
`dist` output folder. Once the local production build and browser QA
pass, connect this GitHub repository to Vercel or use the Vercel CLI to
create a **preview** deployment from the intended branch. Check the
preview visually before promoting or merging. No GitHub Actions required.

Recommended release sequence:

1. Complete `npm run build` and `npm run preview` locally.
2. Inspect desktop, mobile layout, animations, and the 3D drag interaction.
3. Confirm the absence of unreviewed public research numbers and secrets.
4. Deploy the reviewed branch as a Vercel preview.
5. Record the short explainer and link it from GitHub README.
6. Merge only after tests and visual QA have passed.

This public website intentionally has no API credentials, Python service,
live Dhan data connection, or trading execution features.
