"""CLI placeholder for the offline ML pipeline."""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="NCS offline ML pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("validate-features", "train", "predict"):
        subparsers.add_parser(command, help=f"placeholder for {command}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(f"command '{args.command}' is not implemented in Iteration 1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
