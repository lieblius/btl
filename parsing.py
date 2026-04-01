"""Sea-Bird .BTL file parser.

Parses bottle summary files from SBE Data Processing software,
extracting avg values for selected columns (typically Sal00 and DepSM).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd


# ---------------------------------------------------------------------------
# Column name variants (tried in order)
# ---------------------------------------------------------------------------

SALINITY_VARIANTS = ["Sal00", "Sal0", "sal00"]
DEPTH_VARIANTS = ["DepSM", "depSM", "DepS"]
PRESSURE_VARIANTS = ["PrDM", "prDM"]  # fallback for depth
BOTTLE_VARIANTS = ["Btl_Posn", "Bottle"]


@dataclass
class BTLHeader:
    """Metadata extracted from the * and # header lines."""
    star_lines: list[str] = field(default_factory=list)
    hash_lines: list[str] = field(default_factory=list)
    filename: str = ""
    latitude: str = ""
    longitude: str = ""
    cruise_date: str = ""
    station: str = ""


def _fix_concat_columns(line: str) -> str:
    """Fix known SBE column name concatenation bugs.

    SBE software sometimes concatenates adjacent column names, e.g.:
    - FlECO-AFLTurbWETntu0 -> FlECO-AFL TurbWETntu0
    - ...Sbeox0Mm/Kg -> ... Sbeox0Mm/Kg
    """
    line = re.sub(r"(\S)(Sbeox\d)", r"\1 \2", line)
    line = re.sub(r"(\S)(Sbox\d)", r"\1 \2", line)
    line = re.sub(r"(\S)(TurbWET)", r"\1 \2", line)
    return line


def _find_column(columns: list[str], variants: list[str]) -> str | None:
    """Find the first matching column name from a list of variants."""
    for v in variants:
        if v in columns:
            return v
    return None


def parse_header(lines: list[str]) -> tuple[BTLHeader, int]:
    """Parse header lines and return metadata + index of first column name line."""
    header = BTLHeader()
    data_start = 0

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("*"):
            header.star_lines.append(stripped)
            if "NMEA Latitude" in stripped:
                header.latitude = stripped.split("=", 1)[1].strip()
            elif "NMEA Longitude" in stripped:
                header.longitude = stripped.split("=", 1)[1].strip()
            elif "FileName" in stripped and not header.filename:
                header.filename = stripped.split("=", 1)[1].strip()
            elif "NMEA UTC" in stripped:
                header.cruise_date = stripped.split("=", 1)[1].strip()
            elif "System UpLoad Time" in stripped and not header.cruise_date:
                header.cruise_date = stripped.split("=", 1)[1].strip()
        elif stripped.startswith("#"):
            header.hash_lines.append(stripped)
            if "StationNr" in stripped:
                header.station = stripped.split("=", 1)[1].strip()
        else:
            data_start = i
            break

    return header, data_start


def _parse_fwf_positions(header_line: str) -> list[tuple[str, int, int]]:
    """Parse a fixed-width header line to find (column_name, field_start, field_end).

    Returns list of (name, start_index, end_index) where end_index is exclusive.

    Data values are right-aligned under (and around) column names. The field
    for each column extends from the END of the previous column's name to the
    END of this column's name.  The first column's field starts at position 0.
    """
    header_line = _fix_concat_columns(header_line)
    # Find each column name token and its character span
    tokens = [(m.group(), m.start(), m.end()) for m in re.finditer(r"\S+", header_line)]

    result = []
    for i, (name, _start, end) in enumerate(tokens):
        field_start = 0 if i == 0 else tokens[i - 1][2]  # end of previous name
        field_end = end if i + 1 < len(tokens) else None  # None = to end of line
        # For the last column, extend to end of line so we capture all data
        if i + 1 < len(tokens):
            field_end = end
        else:
            field_end = None
        result.append((name, field_start, field_end))

    return result


def parse_column_names(lines: list[str], col_start: int) -> tuple[list[list[tuple[str, int, int]]], int]:
    """Parse column header rows and return column positions + index of first data line.

    Returns (header_rows, data_start_index).
    header_rows is a list of rows, where each row is a list of (name, start, end) tuples.
    Each row corresponds to one physical line of data in a wrapped record.
    """
    header_rows: list[list[tuple[str, int, int]]] = []
    data_start = col_start

    while data_start < len(lines):
        stripped = lines[data_start].strip()
        if not stripped:
            data_start += 1
            continue
        # Data lines start with a digit (bottle number) or are blank-padded + digit
        if stripped[0].isdigit():
            break
        header_rows.append(_parse_fwf_positions(lines[data_start]))
        data_start += 1

    return header_rows, data_start


def _extract_fields_multi(
    data_lines: list[str],
    header_rows: list[list[tuple[str, int, int]]],
) -> dict[str, str]:
    """Extract field values from a multi-line data record using per-row column positions."""
    record = {}
    for row_idx, col_positions in enumerate(header_rows):
        if row_idx >= len(data_lines):
            break
        line = data_lines[row_idx]
        for name, start, end in col_positions:
            if start >= len(line):
                record[name] = ""
                continue
            if end is None:
                raw = line[start:]
            elif end > len(line):
                raw = line[start:]
            else:
                raw = line[start:end]
            val = raw.strip()
            if val:
                record[name] = val
    return record


def parse_btl(text: str) -> tuple[BTLHeader, pd.DataFrame, list[str]]:
    """Parse a .BTL file and return (header, dataframe of avg values, all_columns).

    The dataframe contains one row per bottle with avg values only.
    Handles multi-line wrapped records where columns span multiple physical lines.
    """
    lines = text.splitlines()

    header, col_start = parse_header(lines)
    header_rows, data_start = parse_column_names(lines, col_start)
    col_names = [name for row in header_rows for name, _, _ in row]

    # Collect data lines, grouping by statistic type.
    # Each stat block (avg/sdev/min/max) may span multiple physical lines.
    # The stat label appears at the end of the last physical line in each block.
    avg_records: list[dict[str, str]] = []
    current_lines: list[str] = []

    for i in range(data_start, len(lines)):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            continue

        stat_match = re.search(r"\((avg|sdev|min|max)\)\s*$", stripped)

        if stat_match:
            stat_type = stat_match.group(1)
            # Remove the stat label from this line
            clean_line = line[:line.rfind("(" + stat_type + ")")]
            current_lines.append(clean_line)

            if stat_type == "avg":
                record = _extract_fields_multi(current_lines, header_rows)
                avg_records.append(record)

            current_lines = []
        else:
            current_lines.append(line)

    if not avg_records:
        return header, pd.DataFrame(), col_names

    df = pd.DataFrame(avg_records)
    return header, df, col_names


def extract_bottle_table(
    text: str,
    extra_columns: list[str] | None = None,
) -> tuple[BTLHeader, pd.DataFrame, list[str], dict[str, str]]:
    """Parse BTL and extract a clean table of bottle number + target columns.

    Returns (header, result_df, all_columns, column_mapping).
    column_mapping maps display names to actual column names found.
    """
    header, raw_df, all_columns = parse_btl(text)

    if raw_df.empty:
        return header, pd.DataFrame(), all_columns, {}

    # Find bottle column
    bottle_col = _find_column(all_columns, BOTTLE_VARIANTS)

    # Find target columns
    sal_col = _find_column(all_columns, SALINITY_VARIANTS)
    dep_col = _find_column(all_columns, DEPTH_VARIANTS)
    if dep_col is None:
        dep_col = _find_column(all_columns, PRESSURE_VARIANTS)

    column_mapping: dict[str, str] = {}
    result_cols: dict[str, list] = {"Bottle": []}

    # Extract bottle numbers
    if bottle_col and bottle_col in raw_df.columns:
        result_cols["Bottle"] = pd.to_numeric(raw_df[bottle_col], errors="coerce").astype("Int64").tolist()
    else:
        result_cols["Bottle"] = list(range(1, len(raw_df) + 1))

    # Extract salinity
    if sal_col and sal_col in raw_df.columns:
        column_mapping["Sal00"] = sal_col
        result_cols["Sal00"] = pd.to_numeric(raw_df[sal_col], errors="coerce").tolist()

    # Extract depth
    if dep_col and dep_col in raw_df.columns:
        dep_label = "DepSM" if dep_col in DEPTH_VARIANTS else "PrDM"
        column_mapping[dep_label] = dep_col
        result_cols[dep_label] = pd.to_numeric(raw_df[dep_col], errors="coerce").tolist()

    # Extract any extra requested columns
    if extra_columns:
        for col in extra_columns:
            if col in raw_df.columns:
                column_mapping[col] = col
                result_cols[col] = pd.to_numeric(raw_df[col], errors="coerce").tolist()

    result_df = pd.DataFrame(result_cols)
    return header, result_df, all_columns, column_mapping
