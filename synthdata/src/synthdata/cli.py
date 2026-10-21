"""Command line: ``python -m synthdata generate --seed 20261020 --out data/synthetic/v1``."""

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

from synthdata import GENERATOR_VERSION
from synthdata.config import DEFAULT_SEED
from synthdata.generate import generate
from synthdata.output import write_dataset


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(prog="synthdata")
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate", help="generate the dataset")
    gen.add_argument("--seed", type=int, default=DEFAULT_SEED)
    gen.add_argument("--out", type=Path, default=Path("data/synthetic/v1"))
    gen.add_argument(
        "--if-changed",
        action="store_true",
        help="skip if the manifest already matches seed and version",
    )
    args = parser.parse_args(argv)

    out: Path = args.out
    manifest_path = out / "manifest.json"
    if args.if_changed and manifest_path.exists():
        m = json.loads(manifest_path.read_text(encoding="utf-8"))
        if m.get("seed") == args.seed and m.get("generator_version") == GENERATOR_VERSION:
            print(f"synthdata: {out} is current (seed {args.seed}, v{GENERATOR_VERSION})")
            return 0
    t0 = time.perf_counter()
    ds = generate(args.seed)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    manifest = write_dataset(ds, args.seed, out)
    rows = sum(f["rows"] for f in manifest["files"].values())
    print(
        f"synthdata: wrote {len(manifest['files'])} tables, {rows} rows to {out}"
        f" in {time.perf_counter() - t0:.1f}s"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
