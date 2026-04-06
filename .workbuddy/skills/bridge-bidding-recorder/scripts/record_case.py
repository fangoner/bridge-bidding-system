#!/usr/bin/env python3
"""
Record a bridge bidding case to the bidding-cases directory.

Usage:
    python record_case.py --data '{"hand": {...}, "bidding_sequence": [...], ...}'
    python record_case.py --file case_data.json
"""

import json
import os
import sys
import argparse
from datetime import datetime
from pathlib import Path


def get_project_root():
    """Find the project root directory."""
    # This script is in .workbuddy/skills/bridge-bidding-recorder/scripts/
    # Project root is 4 levels up
    script_dir = Path(__file__).resolve().parent
    return script_dir.parent.parent.parent.parent


def get_next_case_id(cases_dir: Path) -> str:
    """Generate the next case ID based on existing cases."""
    existing_ids = []
    
    if cases_dir.exists():
        for case_file in cases_dir.glob("case-*.json"):
            try:
                case_id = case_file.stem  # "case-001"
                num = int(case_id.split("-")[1])
                existing_ids.append(num)
            except (ValueError, IndexError):
                continue
    
    next_num = max(existing_ids, default=0) + 1
    return f"case-{next_num:03d}"


def load_index(project_root: Path) -> dict:
    """Load or create cases index."""
    index_path = project_root / "bidding-cases" / "cases-index.json"
    
    if index_path.exists():
        with open(index_path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    return {
        "version": "1.0",
        "total_cases": 0,
        "last_updated": datetime.now().isoformat(),
        "cases": [],
        "tag_statistics": {}
    }


def save_index(project_root: Path, index: dict):
    """Save cases index."""
    index_path = project_root / "bidding-cases" / "cases-index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)


def update_tag_statistics(index: dict, tags: list):
    """Update tag statistics in index."""
    if "tag_statistics" not in index:
        index["tag_statistics"] = {}
    
    for tag in tags:
        index["tag_statistics"][tag] = index["tag_statistics"].get(tag, 0) + 1


def record_case(case_data: dict) -> str:
    """
    Record a bidding case.
    
    Args:
        case_data: Dictionary containing case information
        
    Returns:
        Path to the recorded case file
    """
    project_root = get_project_root()
    
    # Get today's date for directory
    today = datetime.now().strftime("%Y-%m-%d")
    cases_dir = project_root / "bidding-cases" / today
    cases_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate case ID
    case_id = get_next_case_id(cases_dir)
    
    # Build complete case record
    case_record = {
        "id": case_id,
        "date": today,
        "timestamp": datetime.now().isoformat(),
        **case_data
    }
    
    # Write case file
    case_file = cases_dir / f"{case_id}.json"
    with open(case_file, "w", encoding="utf-8") as f:
        json.dump(case_record, f, indent=2, ensure_ascii=False)
    
    # Update index
    index = load_index(project_root)
    index["total_cases"] += 1
    index["last_updated"] = datetime.now().isoformat()
    
    # Add to cases list
    case_summary = {
        "id": case_id,
        "date": today,
        "tags": case_data.get("tags", []),
        "brief": case_data.get("discussion_summary", "")[:100] + "..."
    }
    index["cases"].append(case_summary)
    
    # Update tag statistics
    update_tag_statistics(index, case_data.get("tags", []))
    
    save_index(project_root, index)
    
    return str(case_file)


def main():
    parser = argparse.ArgumentParser(description="Record a bridge bidding case")
    parser.add_argument("--data", type=str, help="JSON string with case data")
    parser.add_argument("--file", type=str, help="Path to JSON file with case data")
    
    args = parser.parse_args()
    
    if args.data:
        case_data = json.loads(args.data)
    elif args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            case_data = json.load(f)
    else:
        # Read from stdin
        case_data = json.load(sys.stdin)
    
    case_path = record_case(case_data)
    print(f"Case recorded: {case_path}")


if __name__ == "__main__":
    main()
