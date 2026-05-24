#!/usr/bin/env python
"""One-time import for member first license issue dates.

Run manually from a Heroku one-off dyno:

    python scripts/import_member_license_dates.py "URL" --dry-run
    python scripts/import_member_license_dates.py "URL" --commit

TODO: If model names or field names change, update these imports and constants:
    from app import create_app, db
    from app.members.models import License
    MEMBER_DATE_FIELD = "first_license_issue_date"
    LICENSE_NUMBER_FIELD = "number"
"""

import argparse
import sys
from collections import Counter
from datetime import date
from io import BytesIO
from pathlib import Path

import pandas as pd
import requests
from requests import RequestException
from sqlalchemy.exc import SQLAlchemyError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app, db
from app.members.models import License


REQUIRED_COLUMNS = {
    "license_no",
    "license_begin_date",
}
MEMBER_DATE_FIELD = "first_license_issue_date"
LICENSE_NUMBER_FIELD = "number"
SOURCE_DATE_COLUMN = "license_begin_date"
OPTIONAL_MEMBER_NAME_COLUMN = "member_name"
BATCH_SIZE = 500
DOWNLOAD_TIMEOUT_SECONDS = 120


def parse_args():
    parser = argparse.ArgumentParser(
        description="Import first license issue dates for members from an Excel file."
    )
    parser.add_argument("file_url", help="Direct-download URL for the Excel file.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Validate and summarize without committing.")
    mode.add_argument("--commit", action="store_true", help="Perform updates and commit after all rows are processed.")
    parser.add_argument("--sheet-name", default=0, help="Excel sheet name. Defaults to the first sheet.")
    parser.add_argument("--output-dir", default="import_logs", help="Directory for CSV import logs.")
    return parser.parse_args()


def download_excel(file_url):
    try:
        response = requests.get(file_url, timeout=DOWNLOAD_TIMEOUT_SECONDS)
        response.raise_for_status()
    except RequestException as exc:
        raise RuntimeError(f"Failed to download file: {exc}") from exc

    content_type = response.headers.get("Content-Type", "").lower()
    content = response.content
    if not content:
        raise RuntimeError("Downloaded response is empty.")

    excel_content_types = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
        "application/octet-stream",
        "binary/octet-stream",
    )
    looks_like_excel = content.startswith(b"PK") or content.startswith(b"\xd0\xcf\x11\xe0")
    if content_type and not any(kind in content_type for kind in excel_content_types) and not looks_like_excel:
        raise RuntimeError(f"Downloaded response does not look like an Excel file. Content-Type: {content_type}")

    return BytesIO(content)


def read_excel(workbook, sheet_name):
    try:
        return pd.read_excel(workbook, sheet_name=sheet_name, engine="openpyxl", dtype={"license_no": object})
    except Exception as exc:
        raise RuntimeError(f"Failed to read Excel file: {exc}") from exc


def validate_columns(frame):
    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        columns = ", ".join(sorted(missing))
        raise RuntimeError(f"Missing required column(s): {columns}")


def normalize_license_no(value):
    if pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def parse_issue_date(value):
    if pd.isna(value):
        return None
    if isinstance(value, (int, float)):
        parsed = pd.to_datetime(value, errors="coerce", unit="D", origin="1899-12-30")
        if not pd.isna(parsed):
            return parsed.date()
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def format_log_value(value):
    if isinstance(value, date):
        return value.isoformat()
    if pd.isna(value):
        return ""
    return str(value)


def row_log(
    row_number,
    license_no,
    member_name,
    issue_date,
    reason=None,
    member_id=None,
    existing_date=None,
    raw_issue_date=None,
):
    return {
        "row_number": row_number,
        "license_no": license_no,
        "member_name": member_name,
        "raw_license_begin_date": format_log_value(raw_issue_date),
        "license_begin_date": format_log_value(issue_date),
        MEMBER_DATE_FIELD: format_log_value(issue_date),
        "member_id": member_id,
        "existing_first_license_issue_date": format_log_value(existing_date),
        "reason": reason,
    }


def load_license_map(license_numbers):
    license_map = {}
    for start in range(0, len(license_numbers), BATCH_SIZE):
        batch = license_numbers[start:start + BATCH_SIZE]
        licenses = (
            License.query
            .filter(getattr(License, LICENSE_NUMBER_FIELD).in_(batch))
            .all()
        )
        for license_record in licenses:
            license_map[getattr(license_record, LICENSE_NUMBER_FIELD)] = license_record
    return license_map


def prepare_rows(frame):
    valid_rows = []
    invalid_rows = []

    for index, row in frame.iterrows():
        row_number = int(index) + 2
        license_no = normalize_license_no(row["license_no"])
        member_name = ""
        if OPTIONAL_MEMBER_NAME_COLUMN in frame.columns and not pd.isna(row[OPTIONAL_MEMBER_NAME_COLUMN]):
            member_name = str(row[OPTIONAL_MEMBER_NAME_COLUMN]).strip()
        raw_issue_date = row[SOURCE_DATE_COLUMN]
        issue_date = parse_issue_date(raw_issue_date)

        if not license_no:
            invalid_rows.append(
                row_log(
                    row_number,
                    license_no,
                    member_name,
                    issue_date,
                    "missing license_no",
                    raw_issue_date=raw_issue_date,
                )
            )
            continue
        if not issue_date:
            invalid_rows.append(
                row_log(
                    row_number,
                    license_no,
                    member_name,
                    issue_date,
                    "missing or invalid date",
                    raw_issue_date=raw_issue_date,
                )
            )
            continue

        valid_rows.append({
            "row_number": row_number,
            "license_no": license_no,
            "member_name": member_name,
            "issue_date": issue_date,
        })

    return valid_rows, invalid_rows


def process_rows(valid_rows, dry_run):
    counts = Counter()
    updated_rows = []
    unmatched_rows = []
    conflict_rows = []

    unique_license_numbers = sorted({row["license_no"] for row in valid_rows})
    license_map = load_license_map(unique_license_numbers)

    for start in range(0, len(valid_rows), BATCH_SIZE):
        for row in valid_rows[start:start + BATCH_SIZE]:
            license_no = row["license_no"]
            issue_date = row["issue_date"]
            member_name = row["member_name"]
            row_number = row["row_number"]

            license_record = license_map.get(license_no)
            if not license_record or not license_record.member:
                counts["unmatched"] += 1
                unmatched_rows.append(row_log(row_number, license_no, member_name, issue_date, "license_no not found"))
                continue

            # Match by license number only, then update the associated member.
            member = license_record.member
            existing_date = getattr(member, MEMBER_DATE_FIELD)
            if existing_date is None:
                counts["updated"] += 1
                updated_rows.append(row_log(row_number, license_no, member_name, issue_date, "updated", member.id))
                if not dry_run:
                    setattr(member, MEMBER_DATE_FIELD, issue_date)
                    db.session.add(member)
                continue

            if existing_date == issue_date:
                counts["unchanged"] += 1
                continue

            counts["conflict"] += 1
            conflict_rows.append(
                row_log(row_number, license_no, member_name, issue_date, "existing date differs", member.id, existing_date)
            )

    return counts, updated_rows, unmatched_rows, conflict_rows


def write_log(path, rows, columns):
    frame = pd.DataFrame(rows, columns=columns)
    frame.to_csv(path, index=False)


def write_logs(output_dir, summary, invalid_rows, unmatched_rows, conflict_rows, updated_rows):
    output_dir.mkdir(parents=True, exist_ok=True)
    detail_columns = [
        "row_number",
        "license_no",
        "member_name",
        "raw_license_begin_date",
        "license_begin_date",
        "first_license_issue_date",
        "member_id",
        "existing_first_license_issue_date",
        "reason",
    ]
    write_log(output_dir / "import_summary.csv", [summary], list(summary.keys()))
    write_log(output_dir / "import_invalid_rows.csv", invalid_rows, detail_columns)
    write_log(output_dir / "import_unmatched_rows.csv", unmatched_rows, detail_columns)
    write_log(output_dir / "import_conflict_rows.csv", conflict_rows, detail_columns)
    write_log(output_dir / "import_updated_rows.csv", updated_rows, detail_columns)


def print_summary(summary, output_dir):
    print("\nImport summary")
    print("--------------")
    for key in [
        "total_rows",
        "valid_rows",
        "updated_rows",
        "unchanged_rows",
        "invalid_rows",
        "unmatched_rows",
        "conflict_rows",
    ]:
        print(f"{key}: {summary[key]}")
    print(f"log_directory: {output_dir}")


def print_invalid_rows(invalid_rows):
    if not invalid_rows:
        return

    print("\nInvalid rows")
    print("------------")
    for row in invalid_rows:
        print(
            "row_number={row_number}, license_no={license_no}, "
            "raw_license_begin_date={raw_license_begin_date}, reason={reason}".format(**row)
        )


def rollback_if_possible():
    try:
        db.session.rollback()
    except RuntimeError:
        pass


def main():
    args = parse_args()
    output_dir = Path(args.output_dir)

    try:
        workbook = download_excel(args.file_url)
        frame = read_excel(workbook, args.sheet_name)
        validate_columns(frame)

        app = create_app()
        with app.app_context():
            valid_rows, invalid_rows = prepare_rows(frame)
            counts, updated_rows, unmatched_rows, conflict_rows = process_rows(valid_rows, args.dry_run)

            summary = {
                "mode": "dry-run" if args.dry_run else "commit",
                "total_rows": len(frame),
                "valid_rows": len(valid_rows),
                "updated_rows": counts["updated"],
                "unchanged_rows": counts["unchanged"],
                "invalid_rows": len(invalid_rows),
                "unmatched_rows": counts["unmatched"],
                "conflict_rows": counts["conflict"],
            }

            write_logs(output_dir, summary, invalid_rows, unmatched_rows, conflict_rows, updated_rows)

            if args.dry_run:
                db.session.rollback()
            else:
                db.session.commit()

            print_summary(summary, output_dir)
            print_invalid_rows(invalid_rows)
    except SQLAlchemyError as exc:
        rollback_if_possible()
        print(f"Database error: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        rollback_if_possible()
        print(f"Import failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        rollback_if_possible()
        print(f"Unexpected import failure: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
