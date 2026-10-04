#!/usr/bin/env python3
"""Encode a clip to the library standard: mono MP3, 128 kbps CBR, 44.1 kHz.

Usage:
    python tools/encode.py <source file> <category>/<name>.mp3

The destination is written to sounds/<category>/<name>.mp3. Its entry in
sounds/licenses.json must exist first: ID3 tags (title, artist, comment) come from it.
The script prints duration and RMS level before and after, and exits 2 if the
duration moved by more than 50 ms, the output clips, or the mono downmix is more than
6 dB quieter than the source (a sign of an inverted channel cancelling out). Stereo
sources are averaged (0.5 L + 0.5 R).

Needs ffmpeg and ffprobe on PATH, or the imageio-ffmpeg package (ffmpeg only; ffprobe
is then not needed because sample counts come from ffmpeg's astats filter).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOUNDS = ROOT / "sounds"
LICENSES = SOUNDS / "licenses.json"

FFMPEG_ARGS = ["-ar", "44100", "-codec:a", "libmp3lame", "-b:a", "128k"]
MAX_DURATION_DRIFT = 0.050
MAX_RMS_DROP_DB = 6.0


def find_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg  # type: ignore
    except ImportError:
        sys.exit("error: ffmpeg not found; put it on PATH or pip install imageio-ffmpeg")
    return imageio_ffmpeg.get_ffmpeg_exe()


def measure(ffmpeg: str, path: Path) -> dict:
    """Decoded duration (s), overall RMS and peak (dBFS) and channel layout of a file."""
    out = subprocess.run(
        [ffmpeg, "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0",
         "-af", "astats=measure_perchannel=none", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    ).stderr
    audio = re.search(r"Audio:.*?, (\d+) Hz, ([\w.()]+)", out)
    samples = re.findall(r"Number of samples:\s*(\d+)", out)
    rms = re.findall(r"RMS level dB:\s*(-?[\d.]+|-inf)", out)
    peak = re.findall(r"Peak level dB:\s*(-?[\d.]+|-inf)", out)
    if not (audio and samples and rms and peak):
        sys.exit(f"error: could not measure {path}:\n{out[-2000:]}")
    return {
        "duration": int(samples[-1]) / int(audio.group(1)),
        "rms": float(rms[-1]),
        "peak": float(peak[-1]),
        "layout": audio.group(2),
    }


def downmix_args(layout: str) -> list[str]:
    # ffmpeg's -ac 1 mixes stereo at about 0.707 per channel (up to +3 dB, can clip);
    # average the two channels instead.
    if layout == "stereo":
        return ["-af", "pan=mono|c0=0.5*c0+0.5*c1"]
    return ["-ac", "1"]


def tags_for(rel: str) -> list[str]:
    licenses = json.loads(LICENSES.read_text(encoding="utf-8"))
    meta = licenses.get(rel)
    if meta is None:
        sys.exit(f"error: add an entry for '{rel}' to sounds/licenses.json first")
    attribution = meta.get("attribution", "")
    artist = re.search(r"\bby (.+?), ", attribution)
    bsb = re.search(r"\(ID (\d+)\)", attribution) if "BigSoundBank" in attribution else None
    comment = [meta["license"]]
    if bsb:
        comment.append(f"BigSoundBank {bsb.group(1)}")
    if meta.get("source"):
        comment.append(meta["source"])
    tags = {"title": meta["name"], "comment": ", ".join(comment)}
    if artist:
        tags["artist"] = artist.group(1)
    args: list[str] = []
    for key, value in tags.items():
        args += ["-metadata", f"{key}={value}"]
    return args


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 1
    src = Path(sys.argv[1])
    rel = sys.argv[2].replace("\\", "/")
    if not rel.endswith(".mp3"):
        sys.exit("error: destination must be <category>/<name>.mp3")
    dest = SOUNDS / rel
    dest.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg = find_ffmpeg()
    before = measure(ffmpeg, src)
    tmp = dest.with_suffix(".tmp.mp3")
    subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
         "-map", "0:a:0", "-map_metadata", "-1", *downmix_args(before["layout"]),
         *FFMPEG_ARGS, "-id3v2_version", "3", *tags_for(rel), str(tmp)],
        check=True,
    )
    after = measure(ffmpeg, tmp)
    old_size = dest.stat().st_size if dest.exists() else 0
    tmp.replace(dest)

    drift = after["duration"] - before["duration"]
    drop = before["rms"] - after["rms"]
    flags = []
    if abs(drift) > MAX_DURATION_DRIFT:
        flags.append(f"DURATION drift {drift * 1000:+.0f} ms")
    if drop > MAX_RMS_DROP_DB:
        flags.append(f"RMS drop {drop:.1f} dB (inverted channel?)")
    if after["peak"] >= 0:
        flags.append("CLIPPING")
    print(json.dumps({
        "path": f"sounds/{rel}", "source": before["layout"],
        "durationBefore": round(before["duration"], 3),
        "durationAfter": round(after["duration"], 3),
        "driftMs": round(drift * 1000, 1),
        "rmsDropDb": round(drop, 2), "peakAfterDb": after["peak"],
        "sizeBefore": old_size, "sizeAfter": dest.stat().st_size,
        "flags": flags,
    }))
    return 2 if flags else 0


if __name__ == "__main__":
    sys.exit(main())
