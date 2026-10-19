from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from data_pipeline import DashboardData, DashboardView


SCHEMA_VERSION = 1
FRAME_COLUMNS = {
    "daily": ["data_entrada", "leads_cpf_unicos", "cpfs_pos_lead", "taxa_pos_lead"],
    "reasons": ["categoria", "leads"],
    "production_by_product": ["produto", "contratos", "valor_liberado"],
    "production_by_region": ["regiao", "contratos", "valor_liberado"],
    "production_scope": ["produto", "regiao", "contratos", "valor_liberado"],
    "origin_summary": ["origem", "leads", "cpfs_utilizaveis", "cpfs_pos_lead", "taxa_pos_lead", "contratos", "valor_liberado", "ticket_medio"],
}
KPI_KEYS = {
    "lead_records", "unique_valid_cpfs", "invalid_or_missing_cpf_records",
    "production_postlead_cpfs", "conversion_rate", "contracts", "released_value", "average_ticket",
}
KPI_COUNT_KEYS = {"lead_records", "unique_valid_cpfs", "invalid_or_missing_cpf_records", "production_postlead_cpfs", "contracts"}
OPTIONAL_PRODUCTION_KPI_KEYS = {"production_postlead_cpfs", "conversion_rate", "contracts", "released_value", "average_ticket"}
QUALITY_KEYS = {"lead_records", "unique_valid_cpfs", "invalid_or_missing_cpf_records", "unmapped_origin_records"}
VIEW_KEYS = {"kpis", *FRAME_COLUMNS}
ROOT_KEYS = {"schema_version", "period_start", "period_end", "data_quality", "views"}


class PublicDataError(ValueError):
    """The public aggregate is malformed or contains an unapproved field."""


def _validate_kpis(kpis: Mapping[str, Any]) -> dict[str, Any]:
    if set(kpis) != KPI_KEYS:
        raise PublicDataError("Esquema de KPIs inválido.")
    clean: dict[str, Any] = {}
    for key, value in kpis.items():
        if value is None and key in OPTIONAL_PRODUCTION_KPI_KEYS:
            clean[key] = None
            continue
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise PublicDataError("Valor de KPI inválido.")
        number = float(value)
        if not math.isfinite(number) or number < 0:
            raise PublicDataError("Valor de KPI inválido.")
        if key in KPI_COUNT_KEYS and not number.is_integer():
            raise PublicDataError("Contagem de KPI inválida.")
        clean[key] = int(number) if key in KPI_COUNT_KEYS else number
    return clean


def _json_value(value: Any) -> Any:
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    return value


def _safe_reasons(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.reindex(columns=FRAME_COLUMNS["reasons"]).copy()
    if not result.empty:
        result["categoria"] = result["categoria"].astype(str).str.slice(0, 120)
        result["leads"] = pd.to_numeric(result["leads"], errors="coerce").fillna(0).astype(int)
    return result


def _frame_records(name: str, frame: pd.DataFrame) -> list[dict[str, Any]]:
    allowed = FRAME_COLUMNS[name]
    safe = _safe_reasons(frame) if name == "reasons" else frame.reindex(columns=allowed)
    records = []
    for row in safe.to_dict(orient="records"):
        records.append({key: _json_value(value) for key, value in row.items()})
    return records


def serialize_dashboard_data(data: DashboardData) -> dict[str, object]:
    views: dict[str, object] = {}
    for origin, view in data.views.items():
        if not isinstance(origin, str) or len(origin) > 120:
            raise PublicDataError("Rótulo de origem inválido.")
        record: dict[str, object] = {"kpis": _validate_kpis(view.kpis)}
        for name in FRAME_COLUMNS:
            record[name] = _frame_records(name, getattr(view, name))
        views[origin] = record
    quality = {key: int(data.data_quality.get(key, 0)) for key in QUALITY_KEYS}
    if any(value < 0 for value in quality.values()):
        raise PublicDataError("Indicador de qualidade inválido.")
    return {
        "schema_version": SCHEMA_VERSION,
        "period_start": data.period_start,
        "period_end": data.period_end,
        "data_quality": quality,
        "views": views,
    }


def _validate_records(name: str, records: Any) -> pd.DataFrame:
    if not isinstance(records, list):
        raise PublicDataError("Tabela agregada inválida.")
    columns = FRAME_COLUMNS[name]
    clean_records = []
    for record in records:
        if not isinstance(record, Mapping) or set(record) != set(columns):
            raise PublicDataError("A tabela contém campos não permitidos.")
        clean_records.append({key: _json_value(value) for key, value in record.items()})
    return pd.DataFrame.from_records(clean_records, columns=columns)


def deserialize_dashboard_data(payload: Mapping[str, object]) -> DashboardData:
    if set(payload) != ROOT_KEYS or payload.get("schema_version") != SCHEMA_VERSION:
        raise PublicDataError("Versão ou estrutura do JSON público inválida.")
    raw_quality = payload.get("data_quality")
    raw_views = payload.get("views")
    if not isinstance(raw_quality, Mapping) or set(raw_quality) != QUALITY_KEYS:
        raise PublicDataError("Indicadores de qualidade inválidos.")
    if not isinstance(raw_views, Mapping) or not raw_views:
        raise PublicDataError("Visões agregadas ausentes.")
    quality = {}
    for key, value in raw_quality.items():
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise PublicDataError("Indicadores de qualidade inválidos.")
        quality[key] = value
    views: dict[str, DashboardView] = {}
    for origin, raw_view in raw_views.items():
        if not isinstance(origin, str) or not isinstance(raw_view, Mapping) or set(raw_view) != VIEW_KEYS:
            raise PublicDataError("Visão agregada inválida.")
        kpis = raw_view.get("kpis")
        if not isinstance(kpis, Mapping):
            raise PublicDataError("KPIs ausentes.")
        frames = {name: _validate_records(name, raw_view[name]) for name in FRAME_COLUMNS}
        views[origin] = DashboardView(kpis=_validate_kpis(kpis), **frames)
    start, end = payload.get("period_start"), payload.get("period_end")
    if start is not None and not isinstance(start, str):
        raise PublicDataError("Data inicial inválida.")
    if end is not None and not isinstance(end, str):
        raise PublicDataError("Data final inválida.")
    return DashboardData(views=views, data_quality=quality, period_start=start, period_end=end)


def load_dashboard_data(path: Path) -> DashboardData:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PublicDataError("Não foi possível ler o arquivo agregado público.") from error
    if not isinstance(payload, Mapping):
        raise PublicDataError("Estrutura do JSON público inválida.")
    return deserialize_dashboard_data(payload)
