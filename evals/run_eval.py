"""Evaluate extraction without creating requests or calendar events."""

import argparse
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

FIELDS = ["service_type", "time_window", "contact", "in_scope"]
ROOT = Path(__file__).resolve().parent.parent


def normalize(value):
    if isinstance(value, str):
        return " ".join(value.lower().split())
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["rules", "gemini"],
        default="rules",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Evaluate only the first N cases.",
    )
    args = parser.parse_args()

    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")

    # Disable .env loading before importing the extractor in rules mode.
    if args.mode == "rules":
        os.environ["PYTHON_DOTENV_DISABLED"] = "1"
        os.environ.pop("GEMINI_API_KEY", None)

    from app import extract as extractor

    if args.mode == "gemini":
        if not os.getenv("GEMINI_API_KEY", "").strip():
            parser.error("Gemini mode requires GEMINI_API_KEY in .env")

    cases = json.loads(
        (ROOT / "evals" / "cases.json").read_text(encoding="utf-8")
    )

    for index, case in enumerate(cases, start=1):
        if not isinstance(case, list) or len(case) != 5:
            raise ValueError(f"Case {index} must contain five values")
        if not isinstance(case[0], str):
            raise ValueError(f"Case {index} must start with message text")

    if args.limit is not None:
        cases = cases[:args.limit]

    if not cases:
        raise ValueError("No evaluation cases found")

    hits = Counter({field: 0 for field in FIELDS})
    gemini_hits = Counter({field: 0 for field in FIELDS})
    methods = Counter()
    fallback_reasons = Counter()
    failures = []
    exact_matches = 0
    gemini_exact_matches = 0
    gemini_count = 0

    for index, case in enumerate(cases, start=1):
        text, *expected = case

        if args.mode == "rules":
            got = extractor.validate_fields(extractor.rule_based(text))
            method = "rule_based"
        else:
            got = extractor.extract(text)
            method = got.get("extraction_method", "unknown")

            if method != "llm":
                fallback_reasons[
                    got.get("fallback_reason") or "unknown"
                ] += 1

        methods[method] += 1
        is_gemini = (
            args.mode == "gemini"
            and method == "llm"
            and got.get("extraction_provider") == "gemini"
        )

        if is_gemini:
            gemini_count += 1

        all_correct = True

        for field, expected_value in zip(FIELDS, expected):
            actual_value = got.get(field)
            correct = normalize(actual_value) == normalize(expected_value)

            hits[field] += int(correct)
            if is_gemini:
                gemini_hits[field] += int(correct)

            if not correct:
                all_correct = False
                failures.append({
                    "case": index,
                    "method": method,
                    "field": field,
                    "text": text,
                    "expected": expected_value,
                    "actual": actual_value,
                })

        exact_matches += int(all_correct)
        if is_gemini:
            gemini_exact_matches += int(all_correct)

        print(
            f"Case {index}/{len(cases)}: {method}, "
            f"{'all fields correct' if all_correct else 'mismatch'}",
            flush=True,
        )

    count = len(cases)
    accuracy = {
        field: hits[field] / count for field in FIELDS
    }

    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "mode": args.mode,
        "model": (
            os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
            if args.mode == "gemini"
            else None
        ),
        "case_count": count,
        "method_counts": dict(methods),
        "fallback_reasons": dict(fallback_reasons),
        "pipeline_field_accuracy": accuracy,
        "pipeline_exact_match_accuracy": exact_matches / count,
        "gemini_case_count": gemini_count,
        "gemini_field_accuracy": (
            {
                field: gemini_hits[field] / gemini_count
                for field in FIELDS
            }
            if gemini_count
            else None
        ),
        "gemini_exact_match_accuracy": (
            gemini_exact_matches / gemini_count
            if gemini_count
            else None
        ),
        "failures": failures,
    }

    output_dir = ROOT / "evals" / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{args.mode}.json"
    output_file.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"\nMode: {args.mode}")
    print(f"Cases: {count}")
    print(f"Methods: {dict(methods)}")
    print(f"Fallback reasons: {dict(fallback_reasons)}")

    print("\nPipeline accuracy, including any fallback:")
    for field in FIELDS:
        print(f"{field:13s} {accuracy[field]:.1%}")
    print(f"All fields:   {exact_matches / count:.1%}")

    if args.mode == "gemini":
        print(f"\nSuccessful Gemini extractions: {gemini_count}/{count}")
        if gemini_count:
            print("Accuracy on successful Gemini extractions only:")
            for field in FIELDS:
                print(
                    f"{field:13s} "
                    f"{gemini_hits[field] / gemini_count:.1%}"
                )
        else:
            print("No successful Gemini results to score.")

    print("\nField mismatches:")
    if not failures:
        print("None")
    for failure in failures:
        print(
            f"- Case {failure['case']} [{failure['field']}] "
            f"method={failure['method']} "
            f"expected={failure['expected']!r} "
            f"actual={failure['actual']!r}"
        )

    print(f"\nReport saved: {output_file}")
    print("These results measure extraction, not scheduling or booking.")


if __name__ == "__main__":
    main()