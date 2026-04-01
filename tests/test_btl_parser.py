"""Tests for Sea-Bird .BTL file parser.

Validates parsing against 4 real .btl files from research cruises,
plus edge cases for column detection and concatenation bug fixes.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from parsing import (
    _find_column,
    _fix_concat_columns,
    extract_bottle_table,
    parse_btl,
    parse_header,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _read(name: str) -> str:
    return (DATA_DIR / name).read_text(errors="replace")


# ---------------------------------------------------------------------------
# Column concatenation fix
# ---------------------------------------------------------------------------

class TestFixConcatColumns:
    def test_turb_concat(self):
        assert "FlECO-AFL TurbWETntu0" in _fix_concat_columns("FlECO-AFLTurbWETntu0")

    def test_sbeox_concat(self):
        assert "CStarAt0 Sbeox0Mm/Kg" in _fix_concat_columns("CStarAt0Sbeox0Mm/Kg")

    def test_sbox_concat(self):
        assert "foo Sbox0dV/dT" in _fix_concat_columns("fooSbox0dV/dT")

    def test_no_change_when_already_spaced(self):
        line = "FlECO-AFL TurbWETntu0"
        assert _fix_concat_columns(line) == line

    def test_no_change_normal_line(self):
        line = "Sal00 DepSM PrDM T090C"
        assert _fix_concat_columns(line) == line


# ---------------------------------------------------------------------------
# Column variant finder
# ---------------------------------------------------------------------------

class TestFindColumn:
    def test_finds_first_match(self):
        assert _find_column(["DepSM", "PrDM"], ["DepSM", "DepS"]) == "DepSM"

    def test_finds_second_variant(self):
        assert _find_column(["DepS", "PrDM"], ["DepSM", "DepS"]) == "DepS"

    def test_returns_none_when_missing(self):
        assert _find_column(["PrDM", "T090C"], ["DepSM", "DepS"]) is None


# ---------------------------------------------------------------------------
# Header parsing
# ---------------------------------------------------------------------------

class TestParseHeader:
    def test_msm_header(self):
        text = _read("MSM.btl")
        header, col_start = parse_header(text.splitlines())
        assert header.latitude == "36 03.28 N"
        assert header.longitude == "005 04.49 W"
        assert "V0001F01" in header.filename
        assert col_start > 0

    def test_pos_header(self):
        text = _read("POS.btl")
        header, _ = parse_header(text.splitlines())
        assert header.star_lines  # has some star lines
        assert header.hash_lines  # has some hash lines


# ---------------------------------------------------------------------------
# Full file parsing — MSM.btl (24 bottles, 14 columns)
# ---------------------------------------------------------------------------

class TestParseMSM:
    @pytest.fixture
    def parsed(self):
        return parse_btl(_read("MSM.btl"))

    def test_bottle_count(self, parsed):
        _, df, _ = parsed
        assert len(df) == 24

    def test_columns_found(self, parsed):
        _, _, columns = parsed
        assert "Sal00" in columns
        assert "DepSM" in columns
        assert "T090C" in columns

    def test_concat_bug_fixed(self, parsed):
        _, _, columns = parsed
        assert "TurbWETntu0" in columns
        assert "FlECO-AFL" in columns

    def test_first_bottle_values(self, parsed):
        _, df, _ = parsed
        row = df.iloc[0]
        assert float(row["Sal00"]) == pytest.approx(36.7571, abs=0.001)
        assert float(row["DepSM"]) == pytest.approx(9.936, abs=0.01)

    def test_last_bottle_depth(self, parsed):
        _, df, _ = parsed
        last_depth = float(df.iloc[-1]["DepSM"])
        assert last_depth == pytest.approx(3.086, abs=0.01)


# ---------------------------------------------------------------------------
# Full file parsing — POS.btl (13 bottles, has lat/lon columns)
# ---------------------------------------------------------------------------

class TestParsePOS:
    @pytest.fixture
    def parsed(self):
        return parse_btl(_read("POS.btl"))

    def test_bottle_count(self, parsed):
        _, df, _ = parsed
        assert len(df) == 13

    def test_has_latlon_columns(self, parsed):
        _, _, columns = parsed
        assert "Latitude" in columns
        assert "Longitude" in columns

    def test_first_bottle_salinity(self, parsed):
        _, df, _ = parsed
        assert float(df.iloc[0]["Sal00"]) == pytest.approx(35.6325, abs=0.001)

    def test_deep_bottle_depth(self, parsed):
        _, df, _ = parsed
        # First bottle is deepest (~519m)
        assert float(df.iloc[0]["DepSM"]) == pytest.approx(519.171, abs=0.1)


# ---------------------------------------------------------------------------
# Full file parsing — EMB.btl (2 bottles, dual sensors)
# ---------------------------------------------------------------------------

class TestParseEMB:
    @pytest.fixture
    def parsed(self):
        return parse_btl(_read("EMB.btl"))

    def test_bottle_count(self, parsed):
        _, df, _ = parsed
        assert len(df) == 2

    def test_dual_sensor_columns(self, parsed):
        _, _, columns = parsed
        assert "Sal00" in columns
        assert "Sal11" in columns
        assert "T090C" in columns
        assert "T190C" in columns

    def test_values(self, parsed):
        _, df, _ = parsed
        assert float(df.iloc[0]["Sal00"]) == pytest.approx(7.3207, abs=0.001)
        assert float(df.iloc[0]["DepSM"]) == pytest.approx(6.444, abs=0.01)


# ---------------------------------------------------------------------------
# Full file parsing — SCS.btl (12 bottles, minimal columns)
# ---------------------------------------------------------------------------

class TestParseSCS:
    @pytest.fixture
    def parsed(self):
        return parse_btl(_read("SCS.btl"))

    def test_bottle_count(self, parsed):
        _, df, _ = parsed
        assert len(df) == 12

    def test_minimal_columns(self, parsed):
        _, _, columns = parsed
        assert "Sal00" in columns
        assert "DepSM" in columns

    def test_first_bottle(self, parsed):
        _, df, _ = parsed
        # Verify salinity is in reasonable range
        sal = float(df.iloc[0]["Sal00"])
        assert 30 < sal < 40


# ---------------------------------------------------------------------------
# Full file parsing — RR2602.btl (3 bottles, multi-line wrapped headers)
# ---------------------------------------------------------------------------

class TestParseRR2602:
    """Tests for wide files with column headers spanning 4 rows."""

    @pytest.fixture
    def parsed(self):
        return parse_btl(_read("RR2602.btl"))

    def test_bottle_count(self, parsed):
        _, df, _ = parsed
        assert len(df) == 3

    def test_all_24_columns_found(self, parsed):
        _, _, columns = parsed
        assert len(columns) == 27  # 24 data columns + Bottle + Date + Position/Time

    def test_first_bottle_values(self, parsed):
        _, df, _ = parsed
        row = df.iloc[0]
        assert float(row["Sal00"]) == pytest.approx(34.6798, abs=0.001)
        assert float(row["DepSM"]) == pytest.approx(2712.489, abs=0.01)
        assert float(row["PrDM"]) == pytest.approx(2754.710, abs=0.01)

    def test_second_bottle_values(self, parsed):
        _, df, _ = parsed
        row = df.iloc[1]
        assert float(row["Sal00"]) == pytest.approx(34.6880, abs=0.001)
        assert float(row["DepSM"]) == pytest.approx(2226.409, abs=0.01)

    def test_columns_from_all_header_rows(self, parsed):
        """Columns from all 4 header rows are present."""
        _, _, columns = parsed
        # Row 1 columns
        assert "Sal00" in columns
        assert "DepSM" in columns
        # Row 2 columns
        assert "T090C" in columns
        assert "Latitude" in columns
        # Row 3 columns
        assert "Sbeox0ML/L" in columns
        assert "Sbox0Mm/Kg" in columns
        # Row 4 columns
        assert "Position" in columns

    def test_extraction(self):
        header, df, columns, mapping = extract_bottle_table(_read("RR2602.btl"))
        assert len(df) == 3
        assert "Sal00" in df.columns
        assert "DepSM" in df.columns
        assert header.latitude == "53 25.92 S"
        assert header.longitude == "036 06.90 W"


# ---------------------------------------------------------------------------
# extract_bottle_table integration
# ---------------------------------------------------------------------------

class TestExtractBottleTable:
    def test_msm_extraction(self):
        header, df, columns, mapping = extract_bottle_table(_read("MSM.btl"))
        assert "Bottle" in df.columns
        assert "Sal00" in df.columns
        assert "DepSM" in df.columns
        assert len(df) == 24
        assert mapping["Sal00"] == "Sal00"
        assert mapping["DepSM"] == "DepSM"

    def test_bottle_numbers(self):
        _, df, _, _ = extract_bottle_table(_read("POS.btl"))
        bottles = df["Bottle"].tolist()
        # POS.btl has 13 bottles but skips bottle 9
        assert len(bottles) == 13
        assert bottles[0] == 1
        assert 9 not in bottles  # gap in bottle numbering is real data

    def test_missing_column_graceful(self):
        """A file without salinity should still return other columns."""
        # Fabricate a minimal BTL with no Sal00
        fake_btl = (
            "* Test file\n"
            "# some config\n"
            "  Btl_Posn        Date      DepSM\n"
            "  Btl_ID          Time          \n"
            "      1    Jan 01 2025     10.000 (avg)\n"
            "      2       12:00:00      0.100 (sdev)\n"
        )
        header, df, columns, mapping = extract_bottle_table(fake_btl)
        assert len(df) == 1
        assert "DepSM" in df.columns
        assert "Sal00" not in df.columns

    def test_extra_columns(self):
        _, df, _, mapping = extract_bottle_table(
            _read("MSM.btl"), extra_columns=["T090C"]
        )
        assert "T090C" in df.columns
        assert mapping["T090C"] == "T090C"
