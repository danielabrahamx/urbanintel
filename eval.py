"""
Eval script: run the Gemini pipeline against a labelled clip set and score it.

Usage:
    python eval.py --clips eval_clips/ --labels eval_clips/labels.json

labels.json format:
    {
      "clip_001.mp4": ["NEAR_MISS"],
      "clip_002.mp4": ["DANGEROUS_OVERTAKE"],
      "clip_003.mp4": [],           <- clean clip, no incident
      "clip_004.mp4": ["NEAR_MISS", "CYCLIST_RISK"]
    }

Outputs:
    - Per-clip result table
    - Per-type precision / recall / F1
    - Overall binary precision / recall / F1 (incident vs no incident)
    - Results saved to eval_results.json
"""

import argparse
import json
import os
import sys
import time
import warnings
from datetime import datetime
from pathlib import Path

with warnings.catch_warnings():
    warnings.simplefilter("ignore", FutureWarning)
    import google.generativeai as genai

from dotenv import load_dotenv

from config import VISION_MODEL
from main import ANALYSIS_PROMPT

VALID_TYPES = {
    "NEAR_MISS",
    "RED_LIGHT_VIOLATION",
    "WRONG_WAY",
    "DANGEROUS_OVERTAKE",
    "PEDESTRIAN_IN_ROAD",
    "VEHICLE_STOPPED_DANGEROUSLY",
    "AGGRESSIVE_DRIVING",
    "CYCLIST_RISK",
}


# ---------------------------------------------------------------------------
# Gemini helpers
# ---------------------------------------------------------------------------

def analyse_video(video_path: str) -> dict:
    """Upload, analyse, delete. Returns parsed JSON from Gemini."""
    uploaded_file = None
    try:
        uploaded_file = genai.upload_file(str(video_path), mime_type="video/mp4")

        while uploaded_file.state.name == "PROCESSING":
            time.sleep(2)
            uploaded_file = genai.get_file(uploaded_file.name)

        if uploaded_file.state.name != "ACTIVE":
            raise RuntimeError(f"File processing failed: state={uploaded_file.state.name}")

        model = genai.GenerativeModel(VISION_MODEL)
        response = model.generate_content(
            [uploaded_file, ANALYSIS_PROMPT],
            generation_config={"response_mime_type": "application/json"},
        )
        return json.loads(response.text)

    finally:
        if uploaded_file:
            try:
                genai.delete_file(uploaded_file.name)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    """Return (precision, recall, f1). Safe against zero division."""
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1        = (2 * precision * recall / (precision + recall)
                 if (precision + recall) > 0 else 0.0)
    return precision, recall, f1


def score_clip(ground_truth: list[str], prediction: dict) -> dict:
    """
    Compare ground truth incident types against model prediction.
    Returns per-type TP/FP/FN and binary incident-level result.
    """
    gt_types  = set(ground_truth)
    has_incident_gt = len(gt_types) > 0

    pred_incidents = prediction.get("incidents", [])
    pred_types = {
        inc["type"]
        for inc in pred_incidents
        if inc.get("type") in VALID_TYPES
    }
    has_incident_pred = prediction.get("incident_detected", False)

    type_scores = {}
    for t in VALID_TYPES:
        in_gt   = t in gt_types
        in_pred = t in pred_types
        type_scores[t] = {
            "tp": int(in_gt and in_pred),
            "fp": int((not in_gt) and in_pred),
            "fn": int(in_gt and (not in_pred)),
        }

    return {
        "gt_types":          sorted(gt_types),
        "pred_types":        sorted(pred_types),
        "binary_tp":         int(has_incident_gt and has_incident_pred),
        "binary_fp":         int((not has_incident_gt) and has_incident_pred),
        "binary_fn":         int(has_incident_gt and (not has_incident_pred)),
        "binary_tn":         int((not has_incident_gt) and (not has_incident_pred)),
        "type_scores":       type_scores,
        "severity":          prediction.get("severity", "none"),
        "scene_summary":     prediction.get("scene_summary", ""),
        "reasoning":         prediction.get("reasoning", ""),
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_summary(clip_results: dict, labels: dict) -> None:
    print("\n" + "=" * 70)
    print("EVAL RESULTS")
    print("=" * 70)

    # Per-clip table
    print(f"\n{'Clip':<30} {'GT types':<28} {'Pred types':<28} {'Binary'}")
    print("-" * 95)
    for clip, res in clip_results.items():
        if "error" in res:
            print(f"{clip:<30} ERROR: {res['error']}")
            continue
        gt   = ", ".join(res["gt_types"])  or "clean"
        pred = ", ".join(res["pred_types"]) or "clean"
        binary = ("TP" if res["binary_tp"] else
                  "FP" if res["binary_fp"] else
                  "FN" if res["binary_fn"] else "TN")
        print(f"{clip:<30} {gt:<28} {pred:<28} {binary}")

    # Binary overall
    total_tp = sum(r.get("binary_tp", 0) for r in clip_results.values() if "error" not in r)
    total_fp = sum(r.get("binary_fp", 0) for r in clip_results.values() if "error" not in r)
    total_fn = sum(r.get("binary_fn", 0) for r in clip_results.values() if "error" not in r)
    total_tn = sum(r.get("binary_tn", 0) for r in clip_results.values() if "error" not in r)
    p, r, f1 = prf(total_tp, total_fp, total_fn)

    print(f"\n{'BINARY (incident vs clean)'}")
    print(f"  TP={total_tp}  FP={total_fp}  FN={total_fn}  TN={total_tn}")
    print(f"  Precision={p:.2f}  Recall={r:.2f}  F1={f1:.2f}")

    # Per-type breakdown (only types that appear in ground truth)
    gt_types_used = set()
    for gt_list in labels.values():
        gt_types_used.update(gt_list)

    if gt_types_used:
        print(f"\n{'PER-TYPE BREAKDOWN'}")
        print(f"  {'Type':<35} {'TP':>4} {'FP':>4} {'FN':>4}  {'P':>5}  {'R':>5}  {'F1':>5}")
        print(f"  {'-'*67}")
        for t in sorted(gt_types_used):
            tp = sum(r["type_scores"][t]["tp"] for r in clip_results.values() if "error" not in r)
            fp = sum(r["type_scores"][t]["fp"] for r in clip_results.values() if "error" not in r)
            fn = sum(r["type_scores"][t]["fn"] for r in clip_results.values() if "error" not in r)
            tp_val, r_val, f1_val = prf(tp, fp, fn)
            print(f"  {t:<35} {tp:>4} {fp:>4} {fn:>4}  {tp_val:>5.2f}  {r_val:>5.2f}  {f1_val:>5.2f}")

    print("\n" + "=" * 70)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Eval Gemini pipeline against labelled clips")
    parser.add_argument("--clips",  required=True, help="Folder containing MP4 clips")
    parser.add_argument("--labels", required=True, help="Path to labels.json")
    parser.add_argument("--out",    default="eval_results.json", help="Output JSON path")
    args = parser.parse_args()

    load_dotenv()
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: Set GEMINI_API_KEY in .env")
        sys.exit(1)
    genai.configure(api_key=api_key)

    clips_dir = Path(args.clips)
    if not clips_dir.is_dir():
        print(f"ERROR: clips folder not found: {clips_dir}")
        sys.exit(1)

    with open(args.labels) as f:
        labels: dict[str, list[str]] = json.load(f)

    print(f"Urban Intelligence Eval")
    print(f"  Clips  : {clips_dir}")
    print(f"  Labels : {args.labels}  ({len(labels)} clips)")
    print(f"  Model  : {VISION_MODEL}")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    clip_results = {}
    for i, (clip_name, gt_types) in enumerate(labels.items(), 1):
        clip_path = clips_dir / clip_name
        print(f"[{i}/{len(labels)}] {clip_name}  (GT: {gt_types or ['clean']})")

        if not clip_path.exists():
            print(f"  SKIP: file not found")
            clip_results[clip_name] = {"error": "file not found"}
            continue

        try:
            print("  Uploading...", end=" ", flush=True)
            prediction = analyse_video(clip_path)
            print("done")
            result = score_clip(gt_types, prediction)
            clip_results[clip_name] = result
            binary = ("TP" if result["binary_tp"] else
                      "FP" if result["binary_fp"] else
                      "FN" if result["binary_fn"] else "TN")
            print(f"  Predicted: {result['pred_types'] or ['clean']}  [{binary}]")
            print(f"  Summary  : {result['scene_summary']}")
        except Exception as exc:
            print(f"  ERROR: {exc}")
            clip_results[clip_name] = {"error": str(exc)}

        print()

    print_summary(clip_results, labels)

    out = {
        "run_at": datetime.now().isoformat(),
        "model": VISION_MODEL,
        "clips": clip_results,
    }
    with open(args.out, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nFull results saved to: {args.out}")


if __name__ == "__main__":
    main()
