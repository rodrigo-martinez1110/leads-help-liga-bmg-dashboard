from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from data_pipeline import build_dashboard_data, merge_lead_frames, parse_origin_mapping, read_sources
from public_data import serialize_dashboard_data


ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "dashboard_data_public.json"
DEFAULT_MAPPING = ROOT / "origin_mapping.txt"


def generate_public_artifact(
    leads_paths: list[Path] | Path,
    production_path: Path | None,
    mapping_path: Path,
    destination: Path,
) -> None:
    paths = [leads_paths] if isinstance(leads_paths, Path) else list(leads_paths)
    if not paths:
        raise ValueError("Informe pelo menos um arquivo de leads.")

    first_leads, production = read_sources(paths[0], production_path)
    lead_frames = [first_leads]
    for leads_path in paths[1:]:
        next_leads, embedded_production = read_sources(leads_path)
        lead_frames.append(next_leads)
        if production_path is None and embedded_production is not None:
            production = embedded_production

    leads = merge_lead_frames(lead_frames)
    mapping = parse_origin_mapping(mapping_path.read_text(encoding="utf-8-sig"))
    dashboard = build_dashboard_data(leads, production, mapping)
    payload = serialize_dashboard_data(dashboard)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_name = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=destination.parent, delete=False) as temporary:
            temporary_name = temporary.name
            json.dump(payload, temporary, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
            temporary.write("\n")
        os.replace(temporary_name, destination)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gera o JSON agregado público a partir de relatórios locais.")
    parser.add_argument("--leads", type=Path, nargs="+", required=True, help="Um ou mais arquivos XLSX/CSV/ZIP de leads; registros repetidos são consolidados por Lead.leadId")
    parser.add_argument("--production", type=Path, help="Relatório de produção separado (opcional se estiver dentro do primeiro ZIP)")
    parser.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING, help="Mapeamento local de origens")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Destino do JSON agregado público")
    return parser


def main() -> None:
    args = _parser().parse_args()
    generate_public_artifact(args.leads, args.production, args.mapping, args.output)
    print(f"Agregado público atualizado: {args.output}")


if __name__ == "__main__":
    main()
