"""Trade journal review.

POST /journal/analyze          upload a broker export (.csv or .xlsx); returns profile, behaviour checks, round trips
POST /journal/analyze-sample   the same on a synthetic tradebook, to try the page without a file

The file is read in memory and analysed; nothing is written to disk or kept.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, File, HTTPException, UploadFile

from aletheia.core.journal.analysis import analyze
from aletheia.core.journal.parsers import MAX_BYTES, JournalFormatError, load_table, parse
from aletheia.core.journal.sample import sample_tradebook_csv

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1")


def _run(content: bytes, filename: str) -> dict:
    fmt, df = parse(load_table(content, filename))
    result = analyze(df)
    result["file"] = {
        "name": filename,
        "format": fmt,
        "rows_used": int(len(df)),
        "rows_skipped": int(df.attrs.get("skipped_rows", 0)),
        "date_range": [
            df["datetime"].min().date().isoformat(),
            df["datetime"].max().date().isoformat(),
        ],
    }
    return result


@router.post("/journal/analyze")
async def analyze_journal(file: UploadFile = File(...)) -> dict:
    content = await file.read(MAX_BYTES + 1)
    try:
        return await asyncio.to_thread(_run, content, file.filename or "journal.csv")
    except JournalFormatError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("journal analysis failed")
        raise HTTPException(
            status_code=500,
            detail="The journal could not be analysed. The file may use an unusual layout.",
        ) from exc


@router.post("/journal/analyze-sample")
async def analyze_sample() -> dict:
    result = await asyncio.to_thread(
        _run, sample_tradebook_csv().encode(), "synthetic_tradebook.csv"
    )
    result["synthetic"] = True
    return result
