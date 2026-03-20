import pandas as pd
from fastapi import UploadFile


def load_returns(file: UploadFile) -> pd.Series:
    # Read CSV normally (expects headers)
    df = pd.read_csv(file.file)

    # Validate schema
    if "returns" not in df.columns:
        raise ValueError("CSV must contain a 'returns' column")

    # Extract returns series
    returns = df["returns"]

    return returns
