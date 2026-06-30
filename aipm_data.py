from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Iterable


# What: Data access, validation, and baseline schedule-building utilities for AIPM.
# Purpose: Provide the planning/scheduling agent with a stable contract over D6-style CSV files.

# What: Product/order-level CSV schema.
# Purpose: Identifies the file that describes each WBS order and its due-date level attributes.
PRODUCT_COLUMNS = [
    "日程計画レベル",
    "オーダ状態コード",
    "オーダ計画状況",
    "工程集計ｺｰﾄﾞ",
    "WBS",
    "ﾈｯﾄﾜｰｸ",
    "客先",
    "向先",
    "客先工番",
    "規格",
    "製品名/指図名",
    "管理備考",
    "仕様他",
    "納期",
    "完成日",
    "マイルストン7",
    "立会",
    "オーダ数量",
    "船種名",
    "屯数",
    "スケジュール状態(オーダ単位)",
    "スケジュール結果開始日時(オーダ単位)",
    "スケジュール結果終了日時(オーダ単位)",
    "納期遅延日数",
    "開始可能日前倒し日数",
    "オーダ着手日時",
    "オーダ実績の最終更新日時",
    "オーダ完了日時",
]

# What: Work/activity-level CSV schema.
# Purpose: Identifies the file containing schedulable operations plus hierarchy/grouping rows.
WORK_COLUMNS = [
    "工程集計ｺｰﾄﾞ",
    "WBS",
    "ﾈｯﾄﾜｰｸ",
    "客先",
    "向先",
    "客先工番",
    "製品名/指図名",
    "管理備考",
    "仕様他",
    "納期",
    "完成日",
    "工程計画内外区分",
    "部品NO",
    "部品名称",
    "工程NO",
    "作業工程ID",
    "作業工程名称",
    "作業者ID",
    "作業者名称",
    "作業者必要量",
    "作業工数",
    "工数確認",
    "全体作業LT",
    "作業区分",
    "工程NO変更ロックフラグ",
    "資源引当ON/OFF",
    "確定フラグ",
    "部品数量",
    "基本工区NO",
    "基本工区名称",
    "前段取工数",
    "後段取工数",
    "必要量計算方法",
    "作業工程備考1",
    "作業工程備考2",
    "作業工程備考3",
    "備考集計用",
    "アクティビティの開始可能日(工程計画)",
    "アクティビティの目標終了日(工程計画)",
    "エラーメッセージ",
]

# What: Resource master CSV schema.
# Purpose: Identifies resources, departments, and nominal capacities used for activity assignment.
RESOURCE_COLUMNS = [
    "所属ID",
    "所属名称",
    "資源ID",
    "資源名称",
    "日程計画レベル共通使用区分",
    "資源区分",
    "資源内外区分",
    "ワークパターンNO",
    "実績工数計算用ワークパターンNO",
    "保有量",
    "資源備考1",
    "資源備考2",
    "資源備考3",
    "資源備考4",
    "資源備考5",
    "実績データ出力対象",
    "所属表示順",
    "資源表示順",
    "削除フラグ",
]

# What: Middle-level schedule output schema.
# Purpose: Defines the D6-style CSV shape the planning/scheduling agent should emit.
MIDDLE_SCHEDULE_COLUMNS = [
    "工程集計ｺｰﾄﾞ",
    "WBS",
    "ﾈｯﾄﾜｰｸ",
    "客先工番",
    "製品名/指図名",
    "立会",
    "規格",
    "管理備考",
    "納期",
    "完成日",
    "部品NO",
    "部品名称",
    "基本工区NO",
    "基本工区名称",
    "工程NO",
    "作業工程ID",
    "作業工程名称",
    "工程計画内外区分",
    "進捗率",
    "スケジュール状態",
    "負荷状態",
    "最早最遅逆転救済対象工程",
    "スケジュール結果開始日時",
    "スケジュール結果終了日時",
    "作業者ID",
    "資源ID",
    "資源名称",
    "所属ID",
    "所属名称",
]

# What: Supported datetime input formats.
# Purpose: Normalizes date strings coming from Excel/D6 exports into Python datetimes.
DATETIME_FORMATS = [
    "%Y/%m/%d %H:%M",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d",
    "%Y-%m-%d",
]


# What: A validation finding.
# Purpose: Carries severity and explanation for data contract problems found before scheduling.
@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    message: str


# What: In-memory representation of the AIPM CSV dataset.
# Purpose: Loads, indexes, and validates the files needed by the planning/scheduling agent.
@dataclass
class AIPMDataset:
    product_orders: list[dict[str, str]]
    work_rows: list[dict[str, str]]
    resources: list[dict[str, str]]
    reference_schedule: list[dict[str, str]]

    # What: Dataset factory for a data folder.
    # Purpose: Finds each required CSV by schema so filenames can vary safely.
    @classmethod
    def from_data_dir(cls, data_dir: str | Path = "data") -> "AIPMDataset":
        data_path = Path(data_dir)
        csv_files = list(data_path.glob("*.csv"))
        # Match files by schema rather than by Japanese filename spelling/normalization.
        return cls(
            product_orders=_read_csv(_find_csv(csv_files, PRODUCT_COLUMNS)),
            work_rows=_read_csv(_find_csv(csv_files, WORK_COLUMNS)),
            resources=_read_csv(_find_csv(csv_files, RESOURCE_COLUMNS)),
            reference_schedule=_read_csv(_find_csv(csv_files, MIDDLE_SCHEDULE_COLUMNS)),
        )

    # What: Schedulable activity rows from the work-order file.
    # Purpose: Removes non-operation grouping rows before planning and scheduling.
    @property
    def activities(self) -> list[dict[str, str]]:
        # The work-order file contains grouping rows; only rows with an operation ID are schedulable.
        return [row for row in self.work_rows if row.get("作業工程ID", "").strip()]

    # What: Product/order lookup keyed by WBS.
    # Purpose: Lets activity rows inherit order-level metadata such as due date and inspection flags.
    @property
    def products_by_wbs(self) -> dict[str, dict[str, str]]:
        return {row["WBS"]: row for row in self.product_orders if row.get("WBS")}

    # What: Resource lookup keyed by resource ID.
    # Purpose: Joins activities to resource names, departments, and capacity fields.
    @property
    def resources_by_id(self) -> dict[str, dict[str, str]]:
        return {row["資源ID"]: row for row in self.resources if row.get("資源ID")}

    # What: Dataset-level consistency checks.
    # Purpose: Detect missing schemas, broken WBS/resource joins, and invalid duration strings.
    def validate(self) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        issues.extend(_require_columns("product order", self.product_orders, PRODUCT_COLUMNS))
        issues.extend(_require_columns("work order", self.work_rows, WORK_COLUMNS))
        issues.extend(_require_columns("resource master", self.resources, RESOURCE_COLUMNS))
        issues.extend(
            _require_columns(
                "middle schedule reference",
                self.reference_schedule,
                MIDDLE_SCHEDULE_COLUMNS,
            )
        )

        product_ids = set(self.products_by_wbs)
        resource_ids = set(self.resources_by_id)
        for index, activity in enumerate(self.activities, start=1):
            wbs = activity.get("WBS", "")
            resource_id = activity.get("作業者ID", "")
            if wbs not in product_ids:
                issues.append(ValidationIssue("error", f"activity {index} has unknown WBS: {wbs}"))
            if resource_id not in resource_ids:
                issues.append(
                    ValidationIssue("error", f"activity {index} has unknown resource: {resource_id}")
                )
            for column in ("作業工数", "全体作業LT"):
                try:
                    parse_japanese_duration(activity.get(column, ""))
                except ValueError as exc:
                    issues.append(
                        ValidationIssue("error", f"activity {index} invalid {column}: {exc}")
                    )

        if self.reference_schedule:
            if len(self.activities) != len(self.reference_schedule):
                issues.append(
                    ValidationIssue(
                        "warning",
                        "activity count does not match middle schedule reference: "
                        f"{len(self.activities)} vs {len(self.reference_schedule)}",
                    )
                )
        return issues


# What: Baseline middle-level schedule generator.
# Purpose: Produces a valid schedule-shaped CSV output for testing and future agent improvement.
def build_middle_schedule(dataset: AIPMDataset) -> list[dict[str, str]]:
    """Build a first deterministic, schedule-shaped output from order and resource data.

    This is intentionally simple: it preserves input activity order per WBS, schedules
    forward on weekday 08:00-12:00 and 13:00-17:00 working time, and prevents overlap
    on the same resource. It gives the planning agent a concrete baseline to improve.
    """

    resources = dataset.resources_by_id
    products = dataset.products_by_wbs
    order_available_at: dict[str, datetime] = {}
    resource_available_at: dict[str, datetime] = {}
    output_rows: list[dict[str, str]] = []

    for activity in dataset.activities:
        wbs = activity["WBS"]
        product = products.get(wbs, {})
        resource = resources.get(activity.get("作業者ID", ""), {})
        resource_id = activity.get("作業者ID", "")

        initial_start = (
            parse_datetime(product.get("スケジュール結果開始日時(オーダ単位)", ""))
            or parse_datetime(product.get("オーダ着手日時", ""))
            or parse_datetime(product.get("納期", ""))
            or datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)
        )
        duration_minutes = parse_japanese_duration(activity.get("全体作業LT", ""))
        # This baseline keeps both the order sequence and each resource's queue non-overlapping.
        start = max(
            order_available_at.get(wbs, initial_start),
            resource_available_at.get(resource_id, initial_start),
        )
        start = next_work_time(start)
        end = add_work_minutes(start, duration_minutes)
        order_available_at[wbs] = end
        resource_available_at[resource_id] = end

        output_rows.append(
            {
                "工程集計ｺｰﾄﾞ": activity.get("工程集計ｺｰﾄﾞ", ""),
                "WBS": wbs,
                "ﾈｯﾄﾜｰｸ": activity.get("ﾈｯﾄﾜｰｸ", ""),
                "客先工番": activity.get("客先工番", ""),
                "製品名/指図名": activity.get("製品名/指図名", ""),
                "立会": product.get("立会", ""),
                "規格": product.get("規格", activity.get("規格", "")),
                "管理備考": activity.get("管理備考", ""),
                "納期": _format_due_datetime(activity.get("納期", "")),
                "完成日": activity.get("完成日", ""),
                "部品NO": activity.get("部品NO", ""),
                "部品名称": activity.get("部品名称", ""),
                "基本工区NO": activity.get("基本工区NO", ""),
                "基本工区名称": activity.get("基本工区名称", ""),
                "工程NO": activity.get("工程NO", ""),
                "作業工程ID": activity.get("作業工程ID", ""),
                "作業工程名称": activity.get("作業工程名称", ""),
                "工程計画内外区分": _format_internal_external(
                    activity.get("工程計画内外区分", "")
                ),
                "進捗率": "0.00 ％",
                "スケジュール状態": "0:正常割付",
                "負荷状態": _load_status(activity, resource),
                "最早最遅逆転救済対象工程": "1:対象",
                "スケジュール結果開始日時": format_schedule_datetime(start),
                "スケジュール結果終了日時": format_schedule_datetime(end),
                "作業者ID": resource_id,
                "資源ID": resource_id,
                "資源名称": resource.get("資源名称", activity.get("作業者名称", "")),
                "所属ID": resource.get("所属ID", ""),
                "所属名称": resource.get("所属名称", ""),
            }
        )
    return output_rows


# What: CSV writer for generated middle-level schedule rows.
# Purpose: Preserves the exact output column order expected by downstream D6-style consumers.
def write_middle_schedule(rows: Iterable[dict[str, str]], path: str | Path) -> None:
    with Path(path).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=MIDDLE_SCHEDULE_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


# What: Parser for Japanese duration strings such as "66 時間 00 分".
# Purpose: Converts activity lead times into minutes for scheduling arithmetic.
def parse_japanese_duration(value: str) -> int:
    match = re.search(r"(\d+)\s*時間\s*(\d+)\s*分", value or "")
    if not match:
        raise ValueError(f"expected '<hours> 時間 <minutes> 分', got {value!r}")
    return int(match.group(1)) * 60 + int(match.group(2))


# What: Parser for date and datetime strings used in the CSV exports.
# Purpose: Converts multiple D6/Excel date formats into normalized datetime values.
def parse_datetime(value: str) -> datetime | None:
    clean_value = (value or "").strip()
    if not clean_value:
        return None
    for fmt in DATETIME_FORMATS:
        try:
            parsed = datetime.strptime(clean_value, fmt)
        except ValueError:
            continue
        if fmt in ("%Y/%m/%d", "%Y-%m-%d"):
            return parsed.replace(hour=17, minute=0)
        return parsed
    return None


# What: Formatter for schedule timestamps.
# Purpose: Emits the timestamp style used by the middle-level schedule CSV.
def format_schedule_datetime(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M")


# What: Work-calendar normalizer.
# Purpose: Moves any timestamp outside working time to the next valid work minute.
def next_work_time(value: datetime) -> datetime:
    current = value.replace(second=0, microsecond=0)
    # First version assumes a weekday calendar with two work blocks: 08-12 and 13-17.
    while current.weekday() >= 5:
        current = datetime.combine(current.date() + timedelta(days=1), time(8, 0))
    if current.time() < time(8, 0):
        return datetime.combine(current.date(), time(8, 0))
    if time(12, 0) <= current.time() < time(13, 0):
        return datetime.combine(current.date(), time(13, 0))
    if current.time() >= time(17, 0):
        return next_work_time(datetime.combine(current.date() + timedelta(days=1), time(8, 0)))
    return current


# What: Working-time duration adder.
# Purpose: Advances a start time by minutes while skipping lunch, evenings, and weekends.
def add_work_minutes(start: datetime, minutes: int) -> datetime:
    current = next_work_time(start)
    remaining = minutes
    while remaining > 0:
        block_end = _current_work_block_end(current)
        available = int((block_end - current).total_seconds() // 60)
        if remaining <= available:
            return current + timedelta(minutes=remaining)
        remaining -= available
        current = next_work_time(block_end)
    return current


# What: Current work-block boundary detector.
# Purpose: Finds whether the active block ends at lunch or at end of day.
def _current_work_block_end(value: datetime) -> datetime:
    if value.time() < time(12, 0):
        return datetime.combine(value.date(), time(12, 0))
    return datetime.combine(value.date(), time(17, 0))


# What: UTF-8 CSV reader.
# Purpose: Loads D6/Excel CSV exports into dictionaries while tolerating BOM markers.
def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return [{key: value for key, value in row.items()} for row in csv.DictReader(stream)]


# What: Schema-based CSV finder.
# Purpose: Selects the correct input file without relying on fragile localized filenames.
def _find_csv(files: list[Path], required_columns: list[str]) -> Path:
    for path in files:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            header = next(csv.reader(stream), [])
        # Column signatures are more stable than filenames when files come from D6/Excel exports.
        if all(column in header for column in required_columns):
            return path
    raise FileNotFoundError(f"could not find CSV with columns: {required_columns[:4]}...")


# What: Required-column validator.
# Purpose: Reports missing or empty CSV schemas before downstream scheduling logic runs.
def _require_columns(
    label: str, rows: list[dict[str, str]], required_columns: list[str]
) -> list[ValidationIssue]:
    if not rows:
        return [ValidationIssue("error", f"{label} has no data rows")]
    missing = [column for column in required_columns if column not in rows[0]]
    if missing:
        return [ValidationIssue("error", f"{label} missing columns: {', '.join(missing)}")]
    return []


# What: Due-date output formatter.
# Purpose: Aligns product/order due dates with the schedule CSV timestamp convention.
def _format_due_datetime(value: str) -> str:
    parsed = parse_datetime(value)
    return parsed.strftime("%Y-%m-%d %H:%M") if parsed else value


# What: Internal/external production code formatter.
# Purpose: Converts compact work-order values into D6-style labels such as "内:内製".
def _format_internal_external(value: str) -> str:
    clean_value = value.strip()
    if clean_value in ("内", "内製"):
        return "内:内製"
    if clean_value in ("外", "外製"):
        return "外:外製"
    return clean_value


# What: Simple resource load classifier.
# Purpose: Marks an activity overloaded when required quantity exceeds resource capacity.
def _load_status(activity: dict[str, str], resource: dict[str, str]) -> str:
    try:
        required = float(activity.get("作業者必要量", "") or 0)
        capacity = float(resource.get("保有量", "") or 0)
    except ValueError:
        return "0:PL"
    if capacity and required > capacity:
        return "1:OV"
    return "0:PL"
