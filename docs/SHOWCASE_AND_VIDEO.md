# QuantLab — Source-Labeled Research Demonstration

## What exists now

QuantLab has a fully implemented React/Vite mathematical research front end
and a local FastAPI research engine. The Index Research Studio, 2D/3D charts,
data passports, methodology controls, archived calculations and research
notes have a real browser acceptance workflow on Ubuntu.

The repository now also includes **an opt-in Playwright video recorder**.
On GitHub Actions, the Ubuntu Chromium workflow can also run this recorder
against **only synthetic CI fixtures** and expose its WebM as an expiring
build artifact. A pull-request validation records 100 seconds; a merged-main
run targets **180 seconds**. The artifact is NOT a public video deployment,
is not narrated, and does not certify historical returns. The recorder
**does not submit broker orders**. Review the build artifact before sharing.

## CI recording artifact (after successful browser verification)

Open the latest QuantLab Ubuntu browser acceptance GitHub Actions run and
download the artifact named quantlab-synthetic-three-minute-research-demo.
A merged-main run targets 180 seconds. The video is labeled synthetic,
contains no real Dhan account and is retained for 14 days unless manually
re-exported. A green browser CI only proves this synthetic UI workflow.

## Record a three-minute synthetic demo on Ubuntu

1. Start the current main branch of the real workstation:

       git switch main
       git pull --ff-only origin main
       bash run.sh

2. In a second terminal (repo root), install Playwright *locally*:

       npm install --no-save --no-package-lock --ignore-scripts playwright@1.56.1
       npx playwright install chromium

3. Start recording the only authorized synthetic research environment:

       node scripts/record_quantlab_demo.mjs \
         --url http://127.0.0.1:5173 \
         --seconds 180 \
         --output artifacts/research_demo_first

The script navigates actual React screens, uses the synthetic fixture and
always shows a large visible **SYNTHETIC SOFTWARE DEMO · NOT INDEPENDENTLY
AUDITED** watermark. It writes an unattended local WebM and JSON scope
manifest. It does not fetch Dhan history, trigger trading, endorse or certify
return calculations.

Review the entire recorded tour BEFORE sharing it. The workstation is
local-first and could have private prior research project names: scrub or use
a clean research-data profile before public distribution. Do not publish
client holdings, licensed raw data, broker secrets, or unpublished analyses.

If an MP4 is preferred, convert the reviewed local WebM with ffmpeg:

    ffmpeg -i artifacts/research_demo_first/quantlab-synthetic-research-tour.webm \
      -c:v libx264 -pix_fmt yuv420p \
      artifacts/research_demo_first/quantlab-synthetic-research-tour.mp4

ffmpeg may require a separate local package install.

The captured walkthrough has no narration by design; narration, captions
and empirical paper interpretations should be added only after review.

## What the story can accurately claim

- The simulator implements source-gated factor index construction,
  benchmark-relative covariance risk, execution-lag and cost assumptions.
- Saved runs can be explained at beginner, research and mathematical depth,
  and reproduced from source-pinned evidence.
- Missing original NSE evidence prevents empirical certification.

It **cannot** claim a genuine historical alpha, a validated NSE investment
outcome, live broker fills, or independent audit based on synthetic UI scenes.

The release-status guide is
[QuantLab Evidence and Publication Status](QUANTLAB_STATUS.md).
Use the [research release command](../README.md) to generate a local
source checklist and findings memo if authentic licensed data are available.

## Public showcase

The root Vite project supports an interactive conceptual research story.
Treat its default animated curves and mathematical examples as **illustrative,
not historical NIFTY returns**. Publication is opt-in: review data rights,
charts, visible notices, credentials and the exact build before deployment.
