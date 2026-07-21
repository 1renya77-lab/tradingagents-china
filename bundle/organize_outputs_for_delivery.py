#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parent
OUTPUTS = ROOT / "outputs"
KEEP_DIRS = {"report_pack", "archives"}
SKIP_NAMES = {".DS_Store"}
REPORT_EXTS = {".md", ".png", ".jpg", ".jpeg", ".csv", ".json", ".html"}


def _copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _safe_name(name: str) -> str:
    return str(name).strip().replace("/", "_")


def _run_summary(run_dir: Path) -> list[Path]:
    wanted: list[Path] = []
    for rel in [
        "data_preflight/preflight_data_quality.md",
        "data_source_audit/data_source_audit.md",
    ]:
        path = run_dir / rel
        if path.exists():
            wanted.append(path)
    for folder in ["reports", "signals", "manifests"]:
        path = run_dir / folder
        if path.exists():
            wanted.extend(sorted(path.glob("*")))
    return wanted


def build_report_pack(outputs_dir: Path) -> Path:
    report_pack = outputs_dir / "report_pack"
    if report_pack.exists():
        shutil.rmtree(report_pack)
    report_pack.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []

    guide = outputs_dir / "RESULTS_GUIDE.md"
    if guide.exists():
        _copy_file(guide, report_pack / "RESULTS_GUIDE.md")
        copied.append("RESULTS_GUIDE.md")

    publish_dir = outputs_dir / "publish"
    if publish_dir.exists():
        for path in sorted(publish_dir.rglob("*")):
            if path.is_dir() or path.name in SKIP_NAMES:
                continue
            if path.suffix.lower() not in REPORT_EXTS:
                continue
            rel = path.relative_to(publish_dir)
            _copy_file(path, report_pack / "publish" / rel)
            copied.append(f"publish/{rel}")

    baseline_dir = outputs_dir / "baseline_comparisons"
    if baseline_dir.exists():
        for run_dir in sorted(p for p in baseline_dir.iterdir() if p.is_dir()):
            for path in sorted(run_dir.glob("*")):
                if path.is_dir() or path.name in SKIP_NAMES:
                    continue
                if path.suffix.lower() not in REPORT_EXTS:
                    continue
                _copy_file(path, report_pack / "baseline_comparisons" / run_dir.name / path.name)
                copied.append(f"baseline_comparisons/{run_dir.name}/{path.name}")

    runs_dir = outputs_dir / "runs"
    if runs_dir.exists():
        for run_dir in sorted(p for p in runs_dir.iterdir() if p.is_dir()):
            for path in _run_summary(run_dir):
                if path.is_dir() or path.name in SKIP_NAMES:
                    continue
                if path.suffix.lower() not in REPORT_EXTS:
                    continue
                rel = path.relative_to(run_dir)
                _copy_file(path, report_pack / "runs" / run_dir.name / rel)
                copied.append(f"runs/{run_dir.name}/{rel}")

    top_level_report_dirs = {
        "dashboard": {"index.html", "run_summary.csv", "case_studies.csv", "low_position_stats.csv"},
        "audits": None,
        "data_source_audit": None,
        "provenance": None,
        "mechanism_study_existing": None,
    }
    for dirname, whitelist in top_level_report_dirs.items():
        src_dir = outputs_dir / dirname
        if not src_dir.exists():
            continue
        for path in sorted(src_dir.rglob("*")):
            if path.is_dir() or path.name in SKIP_NAMES:
                continue
            if whitelist is not None and path.name not in whitelist:
                continue
            if path.suffix.lower() not in REPORT_EXTS:
                continue
            rel = path.relative_to(src_dir)
            _copy_file(path, report_pack / dirname / rel)
            copied.append(f"{dirname}/{rel}")

    index_lines = [
        "# Report Pack",
        "",
        "这个目录只保留适合汇报和复查的材料。",
        "",
        "## Included",
        "",
    ]
    index_lines.extend([f"- `{item}`" for item in copied] or ["- (empty)"])
    (report_pack / "README.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")
    return report_pack


def zip_path(src: Path, dst_zip: Path) -> None:
    dst_zip.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(dst_zip, "w", compression=ZIP_DEFLATED) as zf:
        if src.is_file():
            zf.write(src, arcname=src.name)
            return
        for path in sorted(src.rglob("*")):
            if path.is_dir() or path.name in SKIP_NAMES:
                continue
            zf.write(path, arcname=str(path.relative_to(src.parent)))


def build_archives(outputs_dir: Path) -> Path:
    archives = outputs_dir / "archives"
    if archives.exists():
        shutil.rmtree(archives)
    archives.mkdir(parents=True, exist_ok=True)

    for path in sorted(outputs_dir.iterdir()):
        if path.name in KEEP_DIRS or path.name in SKIP_NAMES:
            continue
        if not path.exists():
            continue
        if path.is_dir():
            zip_path(path, archives / f"{_safe_name(path.name)}.zip")
        else:
            zip_path(path, archives / f"{_safe_name(path.stem)}{path.suffix}.zip")
    return archives


def prune_outputs(outputs_dir: Path) -> None:
    for path in sorted(outputs_dir.iterdir()):
        if path.name in KEEP_DIRS or path.name in SKIP_NAMES:
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Organize outputs into a lightweight report pack plus zipped archives.")
    parser.add_argument("--outputs-dir", default=str(OUTPUTS))
    parser.add_argument("--prune", action="store_true", help="Remove original scattered outputs after report_pack and archives are built.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    outputs_dir = Path(args.outputs_dir).expanduser().resolve()
    report_pack = build_report_pack(outputs_dir)
    archives = build_archives(outputs_dir)
    if args.prune:
        prune_outputs(outputs_dir)
    print("Outputs organized for delivery")
    print(f"report_pack : {report_pack}")
    print(f"archives    : {archives}")
    print(f"pruned      : {args.prune}")


if __name__ == "__main__":
    main()
