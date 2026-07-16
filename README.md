# QUANTAREON — Astro Engine

FastAPI + Swiss Ephemeris. Deployed on Render.

## Deploy

1. Push this repo to GitHub
2. Render → New Web Service → select repo
3. Environment → add `QUANTAREON_PASSWORD`

Render reads `render.yaml` automatically.

## Check

Open the engine, enter password, look at the **bottom right corner**:

```
v2 · quantareon-engine.onrender.com   ->  correct, chart will build
v2 · localhost:8000                   ->  wrong API base
no label                              ->  old file, not deployed
```

## What was fixed

The frontend had **three variables named `A`**. The global one (API base)
was shadowed by two others — so the browser called localhost.

Renamed to `QAPI`. 25 call sites updated.

Verified with real Chrome: password, form, "Calculate" — the wheel builds.

## Endpoints

`/natal` `/chart-wheel-natal` `/chart-wheel-transit` `/transit`
`/geocode` `/resolve-place` `/synastry` `/horary` `/cascade` `/interpret`

## Files

```
api/main.py          FastAPI app, password gate, static mount
engine/              natal, cascade, degrees, synastry, horary
astro/               progressions, profections, eclipses
frontend/index.html  the wheel
data/                degree database, ephemeris
render.yaml          Render config
```
