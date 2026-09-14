import gzip
import xml.etree.ElementTree as ET
import csv
from pathlib import Path
from datetime import datetime

def prepare_bpi2012():
    xes_gz_path = Path("BPI_Challenge_2012.xes.gz")
    if not xes_gz_path.exists():
        print(f"Error: {xes_gz_path} not found!")
        return

    out_paths = [
        Path("storage/bpi2012_sample.csv"),
        Path("data/bpi2012_sample.csv"),
    ]
    for p in out_paths:
        p.parent.mkdir(parents=True, exist_ok=True)

    print(f"Parsing {xes_gz_path}...")
    rows = []
    case_count = 0
    max_cases = 100

    with gzip.open(xes_gz_path, "rb") as f:
        # We parse iteratively
        context = ET.iterparse(f, events=("start", "end"))
        current_case_id = None
        current_event = None

        for event, elem in context:
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag

            if event == "start":
                if tag == "trace":
                    current_case_id = None
                elif tag == "event":
                    current_event = {}
            elif event == "end":
                if tag == "string" or tag == "date":
                    key = elem.attrib.get("key")
                    val = elem.attrib.get("value")
                    if current_event is not None:
                        current_event[key] = val
                    elif current_case_id is None and key == "concept:name":
                        current_case_id = val

                elif tag == "event":
                    if current_case_id and current_event:
                        activity = current_event.get("concept:name", "Unknown")
                        ts_str = current_event.get("time:timestamp", "")
                        resource = current_event.get("org:resource", "SYSTEM")
                        if not resource or resource.strip() == "":
                            resource = "SYSTEM"

                        # Standardize timestamp to YYYY-MM-DD HH:MM:SS
                        try:
                            # 2011-10-01T00:38:44.546+02:00
                            dt = datetime.fromisoformat(ts_str)
                            clean_ts = dt.strftime("%Y-%m-%d %H:%M:%S")
                        except Exception:
                            clean_ts = ts_str[:19].replace("T", " ")

                        rows.append({
                            "case_id": current_case_id,
                            "activity": activity,
                            "timestamp": clean_ts,
                            "resource": resource
                        })
                    current_event = None
                    elem.clear()

                elif tag == "trace":
                    case_count += 1
                    elem.clear()
                    if case_count >= max_cases:
                        break

    print(f"Extracted {len(rows)} events across {case_count} cases.")

    for out_path in out_paths:
        with open(out_path, "w", newline="", encoding="utf-8") as out_f:
            writer = csv.DictWriter(out_f, fieldnames=["case_id", "activity", "timestamp", "resource"])
            writer.writeheader()
            writer.writerows(rows)
        print(f"Saved to {out_path} ({out_path.stat().st_size} bytes)")

if __name__ == "__main__":
    prepare_bpi2012()
