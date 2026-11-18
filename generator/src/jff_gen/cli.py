import argparse
import logging
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from pydantic import ValidationError

from .config import Config, load_config
from .context import build_context
from .daily import generate_range, write_dimensions
from .dimensions import DIMENSION_BUILDERS
from .profiling import build_profile
from .sinks import Sink, s3_storage_options


def _parse_date(text: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid date '{text}', expected YYYY-MM-DD") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jff-gen", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--out", required=True, help="local path or fsspec URL, e.g. s3://bucket/raw"
    )
    common.add_argument(
        "--s3-endpoint",
        help="endpoint URL of an S3-compatible server, e.g. http://localhost:8333 "
        "(credentials come from AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY)",
    )
    common.add_argument("--config", type=Path, help="YAML config replacing the packaged default")
    common.add_argument("--seed", type=int)
    common.add_argument("--branches", type=int, help="override number of branches")

    dim = sub.add_parser("dim", parents=[common], help="write one dimension CSV, or all")
    dim.add_argument("table", choices=[*DIMENSION_BUILDERS, "all"])

    gen = sub.add_parser("generate", parents=[common], help="write daily transaction CSVs")
    gen.add_argument("--date", type=_parse_date, help="single date")
    gen.add_argument("--start", type=_parse_date, help="range start (inclusive)")
    gen.add_argument("--end", type=_parse_date, help="range end (inclusive)")
    gen.add_argument("--scale", type=float, help="order volume multiplier, e.g. 0.1 for dev")
    gen.add_argument("--clean", action="store_true", help="disable all injected defects")

    prof = sub.add_parser("profile", help="profile a generated dataset (local path) as Markdown")
    prof.add_argument(
        "--data", required=True, type=Path, help="root folder holding the generated files"
    )
    prof.add_argument("--out", type=Path, help="write Markdown here instead of printing it")
    return parser


def _apply_overrides(cfg: Config, args: argparse.Namespace) -> Config:
    """Apply CLI flags on top of the config and re-validate the result."""
    data = cfg.model_dump()
    for key, value in (
        ("seed", args.seed),
        ("n_branches", args.branches),
        ("scale", getattr(args, "scale", None)),
    ):
        if value is not None:
            data[key] = value
    if getattr(args, "clean", False):
        data["defects"]["enabled"] = False
    return Config.model_validate(data)


def _resolve_dates(parser: argparse.ArgumentParser, args: argparse.Namespace) -> tuple[date, date]:
    if args.date and (args.start or args.end):
        parser.error("use either --date or --start/--end")
    if args.date:
        return args.date, args.date
    if args.start and args.end:
        if args.end < args.start:
            parser.error("--end is before --start")
        return args.start, args.end
    parser.error("give --date or both --start and --end")
    raise SystemExit(2)


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "profile":
        try:
            text = build_profile(args.data)
        except FileNotFoundError as exc:
            parser.error(str(exc))
        if args.out:
            args.out.write_text(text, encoding="utf-8", newline="\n")
        else:
            print(text)
        return 0
    try:
        cfg = _apply_overrides(load_config(args.config), args)
    except ValidationError as exc:
        details = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
        parser.error(f"invalid settings: {details}")
    ctx = build_context(cfg)
    if args.s3_endpoint and not args.out.startswith("s3://"):
        parser.error("--s3-endpoint needs an s3:// URL for --out")
    options = s3_storage_options(args.s3_endpoint) if args.s3_endpoint else None
    sink = Sink(args.out, options)
    if args.command == "dim":
        write_dimensions(ctx, sink, None if args.table == "all" else args.table)
        return 0
    start, end = _resolve_dates(parser, args)
    generate_range(ctx, start, end, sink)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
