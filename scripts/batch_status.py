import argparse, json, os, sys
from typing import Optional

# Ensure project root added
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from openai import OpenAI
from src.llmchess_simple.config import SETTINGS


def main():
    ap = argparse.ArgumentParser(description="Inspect an OpenAI Batch job and optionally download outputs.")
    ap.add_argument("batch_id", help="The batch ID, e.g. batch_abc123")
    ap.add_argument("--download-out", metavar="PATH", help="If completed, download output file to PATH")
    ap.add_argument("--download-error", metavar="PATH", help="If failed, download error file to PATH")
    args = ap.parse_args()

    client = OpenAI(api_key=SETTINGS.openai_api_key)
    b = client.batches.retrieve(args.batch_id)
    # Print a compact JSON summary
    summary = {
        "id": getattr(b, "id", None),
        "status": getattr(b, "status", None),
        "endpoint": getattr(b, "endpoint", None),
        "input_file_id": getattr(b, "input_file_id", None),
        "output_file_id": getattr(b, "output_file_id", None),
        "error_file_id": getattr(b, "error_file_id", None),
        "created_at": getattr(b, "created_at", None),
        "in_progress_at": getattr(b, "in_progress_at", None),
        "completed_at": getattr(b, "completed_at", None),
        "failed_at": getattr(b, "failed_at", None),
        "expired_at": getattr(b, "expired_at", None),
        "request_counts": getattr(b, "request_counts", None),
        "metadata": getattr(b, "metadata", None),
    }
    print(json.dumps(summary, indent=2))

    # Optionally download outputs
    if args.download_out and getattr(b, "output_file_id", None):
        fobj = client.files.content(b.output_file_id)
        data = getattr(fobj, "text", None) or getattr(fobj, "content", None)
        if isinstance(data, bytes):
            data = data.decode("utf-8", errors="replace")
        with open(args.download_out, "w", encoding="utf-8") as f:
            f.write(data or "")
        print(f"Wrote output to {args.download_out}")

    if args.download_error and getattr(b, "error_file_id", None):
        fobj = client.files.content(b.error_file_id)
        data = getattr(fobj, "text", None) or getattr(fobj, "content", None)
        if isinstance(data, bytes):
            data = data.decode("utf-8", errors="replace")
        with open(args.download_error, "w", encoding="utf-8") as f:
            f.write(data or "")
        print(f"Wrote error to {args.download_error}")


if __name__ == "__main__":
    main()
