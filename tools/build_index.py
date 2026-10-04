#!/usr/bin/env python3
"""Regenerate index.json from the sounds/ tree and sounds/licenses.json.

Usage:
    python tools/build_index.py          # write index.json
    python tools/build_index.py --check  # exit 1 if index.json is stale or metadata is missing

Standard library only, so it runs unchanged in CI and on any workstation.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOUNDS = ROOT / "sounds"
LICENSES = SOUNDS / "licenses.json"
INDEX = ROOT / "index.json"
SCHEMA = 1

AUDIO_EXTS = {".wav": "wav", ".mp3": "mp3"}

# Licences that allow public redistribution. CC-BY variants need an attribution.
ALLOWED_LICENSES = {"CC0-1.0", "Public-Domain", "CC-BY-3.0", "CC-BY-4.0"}
ATTRIBUTION_REQUIRED = {"CC-BY-3.0", "CC-BY-4.0"}

# MRCS stores clips as /sounds/<filename> on SPIFFS and rejects names of 96+ characters.
FILENAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,95}$")
CATEGORY_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class MetadataError(Exception):
    pass


def wav_info(path: Path) -> tuple[float, int, int]:
    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2:
            raise MetadataError(f"{path}: WAV must be 16-bit PCM (MRCS playback requirement)")
        if w.getnchannels() not in (1, 2):
            raise MetadataError(f"{path}: WAV must be mono or stereo")
        rate = w.getframerate()
        return w.getnframes() / rate, rate, w.getnchannels()


_MP3_BITRATES = {
    1: [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320],
    2: [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160],
}
_MP3_RATES = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}


def _mp3_header(b: bytes):
    """Decode an MPEG Layer III frame header. Returns (frame_len, rate, channels, samples) or None."""
    if len(b) < 4 or b[0] != 0xFF or (b[1] & 0xE0) != 0xE0:
        return None
    version = (b[1] >> 3) & 3
    layer = (b[1] >> 1) & 3
    br_idx = b[2] >> 4
    sr_idx = (b[2] >> 2) & 3
    if version == 1 or layer != 1 or br_idx in (0, 15) or sr_idx == 3:
        return None
    mpeg1 = version == 3
    bitrate = _MP3_BITRATES[1 if mpeg1 else 2][br_idx] * 1000
    rate = _MP3_RATES[version][sr_idx]
    padding = (b[2] >> 1) & 1
    channels = 1 if (b[3] >> 6) == 3 else 2
    samples = 1152 if mpeg1 else 576
    frame_len = (144 if mpeg1 else 72) * bitrate // rate + padding
    return frame_len, rate, channels, samples


def mp3_info(path: Path) -> tuple[float, int, int]:
    data = path.read_bytes()
    pos = 0
    if data[:3] == b"ID3" and len(data) >= 10:
        size = (data[6] << 21) | (data[7] << 14) | (data[8] << 7) | data[9]
        pos = 10 + size + (10 if data[5] & 0x10 else 0)
    end = len(data) - (128 if data[-128:-125] == b"TAG" else 0)

    frames = total_samples = 0
    rate = channels = 0
    first = True
    while pos + 4 <= end:
        hdr = _mp3_header(data[pos:pos + 4])
        if hdr is None:
            pos += 1
            continue
        frame_len, f_rate, f_channels, samples = hdr
        if first:
            rate, channels = f_rate, f_channels
            # A Xing/Info frame carries encoder metadata and no audio.
            if b"Xing" in data[pos:pos + 64] or b"Info" in data[pos:pos + 64]:
                first = False
                pos += frame_len
                continue
            first = False
        frames += 1
        total_samples += samples
        pos += frame_len
    if frames == 0:
        raise MetadataError(f"{path}: no MPEG Layer III frames found")
    return total_samples / rate, rate, channels


def load_licenses() -> dict:
    if not LICENSES.exists():
        raise MetadataError(f"{LICENSES.relative_to(ROOT)} is missing")
    with LICENSES.open(encoding="utf-8") as f:
        return json.load(f)


def build_sounds() -> list[dict]:
    licenses = load_licenses()
    errors: list[str] = []
    sounds: list[dict] = []
    seen_ids: dict[str, str] = {}
    files = sorted(p for p in SOUNDS.rglob("*") if p.is_file() and p.suffix.lower() in AUDIO_EXTS)
    used_keys = set()

    for path in files:
        rel = path.relative_to(SOUNDS).as_posix()
        parts = rel.split("/")
        if len(parts) != 2:
            errors.append(f"sounds/{rel}: must live directly in sounds/<category>/")
            continue
        category, filename = parts
        if not CATEGORY_RE.match(category):
            errors.append(f"sounds/{rel}: category must be lowercase letters, digits and '-'")
        if not FILENAME_RE.match(filename):
            errors.append(f"sounds/{rel}: filename must be under 96 characters of [A-Za-z0-9_.-]")

        meta = licenses.get(rel)
        if meta is None:
            errors.append(f"sounds/{rel}: no entry in sounds/licenses.json")
            continue
        used_keys.add(rel)
        lic = (meta.get("license") or "").strip()
        attribution = (meta.get("attribution") or "").strip()
        name = (meta.get("name") or "").strip()
        if not name:
            errors.append(f"sounds/{rel}: licenses.json entry needs a 'name'")
        if lic not in ALLOWED_LICENSES:
            errors.append(f"sounds/{rel}: licence '{lic}' is not one of {sorted(ALLOWED_LICENSES)}")
        if lic in ATTRIBUTION_REQUIRED and not attribution:
            errors.append(f"sounds/{rel}: {lic} needs an 'attribution'")

        sound_id = path.stem.lower()
        if sound_id in seen_ids:
            errors.append(f"sounds/{rel}: id '{sound_id}' also used by {seen_ids[sound_id]}")
        seen_ids[sound_id] = f"sounds/{rel}"

        fmt = AUDIO_EXTS[path.suffix.lower()]
        try:
            duration, rate, channels = (wav_info if fmt == "wav" else mp3_info)(path)
        except (MetadataError, wave.Error, EOFError) as e:
            errors.append(str(e))
            continue

        entry = {
            "id": sound_id,
            "name": name,
            "category": category,
            "format": fmt,
            "durationSec": round(duration, 2),
            "sizeBytes": path.stat().st_size,
            "sampleRate": rate,
            "channels": channels,
            "license": lic,
            "attribution": attribution,
            "path": f"sounds/{rel}",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        if meta.get("source"):
            entry["source"] = meta["source"]
        sounds.append(entry)

    for key in sorted(set(licenses) - used_keys):
        errors.append(f"sounds/licenses.json: entry '{key}' has no matching file")

    if errors:
        raise MetadataError("\n".join(errors))
    sounds.sort(key=lambda s: (s["category"], s["id"]))
    return sounds


def render(sounds: list[dict], generated: str) -> str:
    doc = {"schema": SCHEMA, "generated": generated, "baseUrl": "", "sounds": sounds}
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="fail if index.json is out of date")
    args = ap.parse_args()

    try:
        sounds = build_sounds()
    except MetadataError as e:
        print(f"error:\n{e}", file=sys.stderr)
        return 1

    current = None
    if INDEX.exists():
        with INDEX.open(encoding="utf-8") as f:
            current = json.load(f)

    # "generated" only moves when the catalogue changes, so --check is stable.
    unchanged = current is not None and current.get("schema") == SCHEMA and current.get("sounds") == sounds
    if args.check:
        if not unchanged or current.get("baseUrl") != "":
            print("error: index.json is stale; run python tools/build_index.py and commit it", file=sys.stderr)
            return 1
        print(f"index.json is up to date ({len(sounds)} sounds)")
        return 0

    if unchanged:
        print(f"index.json already up to date ({len(sounds)} sounds)")
        return 0
    generated = dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
    INDEX.write_text(render(sounds, generated), encoding="utf-8", newline="\n")
    print(f"wrote index.json ({len(sounds)} sounds)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
