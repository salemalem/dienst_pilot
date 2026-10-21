from pathlib import Path

import polars as pl


def read(root: Path, name: str) -> pl.DataFrame:
    return pl.read_parquet(root / f"{name}.parquet")
