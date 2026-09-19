#!/usr/bin/env python3
"""
Render the narration segments to audio with ElevenLabs.

The page can read itself aloud. Each segment in narration/ is one
view, so the audio follows the reader down the page rather than
running on its own clock and drifting out of step with what is on
screen.

    export ELEVENLABS_API_KEY='sk_...'
    python3 make_narration.py --voices          # pick a voice
    python3 make_narration.py --models          # see what is current
    python3 make_narration.py --voice <voice_id>

Writes audio/00-opening.mp3 ... audio/04-rates.mp3. Existing files are
skipped unless --force, so a re-run after fixing one segment does not
spend credits on the other four.

Standard library only, like the other fetch scripts here: the point of
this repo is that someone can clone it and run everything without
installing anything.
"""

import argparse
import json
import os
import pathlib
import ssl
import sys
import urllib.error
import urllib.request

API = "https://api.elevenlabs.io/v1"


def ssl_context():
    """A context that can actually verify ElevenLabs' certificate.

    The python.org macOS builds ship without a CA bundle wired up —
    ssl.get_default_verify_paths().cafile is None — so every HTTPS
    request from them dies with CERTIFICATE_VERIFY_FAILED until you
    run "Install Certificates.command". certifi is usually sitting
    there already, so point at it when the default is empty.

    Verification stays ON. Turning it off would make this work
    everywhere and mean nothing, which is not a trade worth making
    for an API key in a header.
    """
    if ssl.get_default_verify_paths().cafile:
        return ssl.create_default_context()

    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()

    return ssl.create_default_context(cafile=certifi.where())

# Free, from the ElevenLabs dashboard. Kept in the environment rather
# than in this file, so the key never lands in the repository.
API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")

SRC_DIR = pathlib.Path("narration")
OUT_DIR = pathlib.Path("audio")


def call(path, payload=None, params=""):
    """One request. Returns raw bytes; the caller knows what they are."""
    req = urllib.request.Request(
        f"{API}/{path}{params}",
        data=json.dumps(payload).encode() if payload else None,
        headers={
            "xi-api-key": API_KEY,
            "Content-Type": "application/json",
            "Accept": "*/*",
        },
        method="POST" if payload else "GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=300, context=ssl_context()) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf8", "replace")[:600]
        raise SystemExit(f"\n  HTTP {e.code} from {path}\n  {body}\n")
    except urllib.error.URLError as e:
        if "CERTIFICATE_VERIFY" in str(e.reason):
            raise SystemExit(
                "\n  This Python cannot verify HTTPS certificates.\n"
                "  Fix it once, for every script on this machine:\n"
                "    open '/Applications/Python 3.13/Install Certificates.command'\n")
        raise


def listing(kind):
    """Print the account's voices or the current model ids.

    Here because model identifiers and the voice library both change,
    and a hardcoded guess that used to work is worse than no default
    at all: it fails at the moment you need it.
    """
    data = json.loads(call(kind).decode())
    rows = data.get("voices") if kind == "voices" else data

    for row in rows:
        if kind == "voices":
            print(f"  {row['voice_id']}  {row.get('name','')}")
        else:
            can_tts = row.get("can_do_text_to_speech", True)
            if can_tts:
                print(f"  {row.get('model_id')}  {row.get('name','')}")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--voice", help="voice_id to speak with")
    ap.add_argument("--model", default="eleven_multilingual_v2",
                    help="model id; run --models if this one is rejected")
    ap.add_argument("--format", default="mp3_44100_128")
    ap.add_argument("--voices", action="store_true", help="list voices and exit")
    ap.add_argument("--models", action="store_true", help="list models and exit")
    ap.add_argument("--force", action="store_true", help="re-render existing files")
    args = ap.parse_args()

    if not API_KEY:
        raise SystemExit(
            "ELEVENLABS_API_KEY is not set. Run:\n"
            "  export ELEVENLABS_API_KEY='sk_...'")

    if args.voices:
        return listing("voices")
    if args.models:
        return listing("models")

    if not args.voice:
        raise SystemExit(
            "Pick a voice first:\n"
            "  python3 make_narration.py --voices\n"
            "  python3 make_narration.py --voice <voice_id>")

    segments = sorted(SRC_DIR.glob("*.txt"))
    if not segments:
        raise SystemExit(f"no segments in {SRC_DIR}/")

    OUT_DIR.mkdir(exist_ok=True)
    total = 0

    for seg in segments:
        out = OUT_DIR / (seg.stem + ".mp3")

        if out.exists() and not args.force:
            print(f"  {out}  exists, skipping", file=sys.stderr)
            continue

        text = seg.read_text(encoding="utf8").strip()
        total += len(text)
        print(f"  {seg.name}  {len(text):,} characters", file=sys.stderr)

        audio = call(f"text-to-speech/{args.voice}",
                     payload={"text": text, "model_id": args.model},
                     params=f"?output_format={args.format}")
        out.write_bytes(audio)
        print(f"    wrote {out}  ({len(audio)/1024:.0f} KB)", file=sys.stderr)

    print(f"\n  {total:,} characters rendered", file=sys.stderr)
    print("  The page picks the files up on its own; nothing else to wire.",
          file=sys.stderr)


if __name__ == "__main__":
    main()
