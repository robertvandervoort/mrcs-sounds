# MRCS sound library

Sound clips for MRCS model railway control units, published with GitHub Pages:

- Browse: <https://robertvandervoort.github.io/mrcs-sounds/>
- Manifest: <https://robertvandervoort.github.io/mrcs-sounds/index.json>

MRCS units read `index.json` and download clips from here. Every clip in this
repository can be redistributed publicly.

## Licences

**Each sound has its own licence**, recorded per file in `index.json` (`license`
and `attribution`) and in `sounds/licenses.json`. Only clips under one of these
licences are accepted:

| `license` | Meaning | Attribution |
| --- | --- | --- |
| `CC0-1.0` | Creative Commons Zero | Optional (recorded when known) |
| `Public-Domain` | Public domain | Optional |
| `CC-BY-3.0`, `CC-BY-4.0` | Creative Commons Attribution | Required; reproduce the `attribution` text |

Clips recorded by the maintainer use one of the licences above. Clips whose origin
or licence is unknown are not added. Pixabay content is not accepted: the Pixabay
licence forbids redistributing files on their own.

The tooling, page and workflow (everything outside `sounds/`) are under the
[MIT licence](LICENSE).

## Layout

```
sounds/<category>/<file>   Clips (.mp3 or .wav), one folder per category
sounds/licenses.json       Name, licence, attribution and source for every clip
index.json                 Generated manifest (do not edit by hand)
tools/build_index.py       Regenerates and checks index.json
index.html, assets/        Browse page (no frameworks, no external requests)
.nojekyll                  Serve the tree as-is
```

## Manifest (`index.json`, schema 1)

```json
{
  "schema": 1,
  "generated": "2026-10-04T13:11:54-05:00",
  "baseUrl": "",
  "sounds": [
    {
      "id": "steam-train-horn-hiss",
      "name": "Steam train horn and hiss",
      "category": "railway",
      "format": "mp3",
      "durationSec": 7.78,
      "sizeBytes": 125421,
      "sampleRate": 44100,
      "channels": 1,
      "license": "CC0-1.0",
      "attribution": "...",
      "path": "sounds/railway/steam-train-horn-hiss.mp3",
      "sha256": "...",
      "source": "https://bigsoundbank.com/"
    }
  ]
}
```

- `baseUrl` is empty: resolve `path` against the URL `index.json` was fetched from.
  That keeps the manifest valid on `github.io` and on a custom domain.
- `id` is the filename without its extension and is unique across categories.
- `durationSec` counts MP3 frames, so it can be a frame (about 26 ms) longer than
  players that trim encoder padding.
- `sha256` lets a unit verify a download. `source` is optional.
- `generated` changes only when the list of sounds changes.

## Adding a sound

1. Check the licence is one of those above and note the author and source.
2. Put the file in `sounds/<category>/`. Category folders are lowercase
   (`ambient`, `industry`, `nature`, `railway`, `station`, `effects`, ...). Filenames must be
   under 96 characters of `A-Z a-z 0-9 _ - .`, because MRCS stores clips as
   `/sounds/<filename>`.
3. Prefer what MRCS plays best: 128 kbps mono MP3, or 16-bit PCM WAV (mono or stereo).
4. Add an entry to `sounds/licenses.json`, keyed by the path under `sounds/`:

   ```json
   "railway/my-clip.mp3": {
     "name": "Readable name",
     "license": "CC-BY-4.0",
     "attribution": "\"Title\" by Author, https://example.org/source",
     "source": "https://example.org/source"
   }
   ```

5. Regenerate and commit the manifest:

   ```sh
   python tools/build_index.py
   ```

`tools/build_index.py` uses only the Python standard library (3.9+). With
`--check` it changes nothing and exits 1 if `index.json` is stale, if a clip has no
`licenses.json` entry, if a licence is not allowed, if a CC-BY clip has no
attribution, or if a `licenses.json` entry has no file. The **Check index**
GitHub Actions workflow runs `--check` on every push and pull request.

## Hosting and CORS

GitHub Pages serves the `main` branch root and sends
`Access-Control-Allow-Origin: *` on every file, so the MRCS web UI on a unit
(served from the unit's own address) can fetch `index.json` and clips directly.

### Custom domain (`sounds.vdvlabs.ai`)

Not configured yet. To set it up:

1. In DNS for `vdvlabs.ai`, add a `CNAME` record: `sounds` ->
   `robertvandervoort.github.io` (no path, no trailing `/mrcs-sounds`).
2. In this repository's **Settings > Pages > Custom domain**, enter
   `sounds.vdvlabs.ai` and save. GitHub commits a `CNAME` file to `main`, or run:

   ```sh
   gh api repos/robertvandervoort/mrcs-sounds/pages -X PUT -f cname=sounds.vdvlabs.ai
   ```

3. Wait for the DNS check and certificate, then tick **Enforce HTTPS**
   (`gh api repos/robertvandervoort/mrcs-sounds/pages -X PUT -F https_enforced=true`).
4. Optionally verify the domain under your account's **Settings > Pages** to stop
   other repositories from claiming it.

The site then lives at `https://sounds.vdvlabs.ai/` (no `/mrcs-sounds` prefix) and
`github.io` URLs redirect to it. Paths in `index.json` are relative, so nothing in
the manifest changes.
