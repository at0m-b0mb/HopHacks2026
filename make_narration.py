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
    ap.add_argument("--src", default="narration", help="folder of .txt segments")
    ap.add_argument("--out", default="audio", help="folder to write .mp3 into")

    ap.add_argument("--stability", type=float,
                    help="0 is most expressive, 1 is most consistent. "
                         "Lower it for a warmer, more varied read.")
    ap.add_argument("--similarity", type=float, default=0.75)
    ap.add_argument("--style", type=float,
                    help="0 to 1. Raise it for more performance in the delivery.")
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

    src_dir = pathlib.Path(args.src)
    out_dir = pathlib.Path(args.out)

    segments = sorted(src_dir.glob("*.txt"))
    if not segments:
        raise SystemExit(f"no segments in {src_dir}/")

    out_dir.mkdir(parents=True, exist_ok=True)
    total = 0

    for seg in segments:
        out = out_dir / (seg.stem + ".mp3")

        if out.exists() and out.stat().st_size > 0 and not args.force:
            print(f"  {out}  exists, skipping", file=sys.stderr)
            continue

        text = seg.read_text(encoding="utf8").strip()
        total += len(text)
        print(f"  {seg.name}  {len(text):,} characters", file=sys.stderr)

        payload = {"text": text, "model_id": args.model}

        # Only sent when asked for, so the voice's own defaults stand
        # otherwise. Lower stability reads warmer and less even, which
        # suits a narration meant to be listened to rather than
        # checked.
        if args.stability is not None or args.style is not None:
            payload["voice_settings"] = {
                "stability": 0.4 if args.stability is None else args.stability,
                "similarity_boost": args.similarity,
                "style": 0.0 if args.style is None else args.style,
                "use_speaker_boost": True,
            }

        audio = call(f"text-to-speech/{args.voice}",
                     payload=payload,
                     params=f"?output_format={args.format}")

        # Written aside and moved into place, so an interrupted run
        # cannot leave a truncated mp3 that the skip-if-exists check
        # above then treats as finished on every later run.
        tmp = out.with_suffix(".mp3.part")
        tmp.write_bytes(audio)
        os.replace(tmp, out)
        print(f"    wrote {out}  ({len(audio)/1024:.0f} KB)", file=sys.stderr)

    print(f"\n  {total:,} characters rendered", file=sys.stderr)
    print("  The page picks the files up on its own; nothing else to wire.",
          file=sys.stderr)


if __name__ == "__main__":
    main()
