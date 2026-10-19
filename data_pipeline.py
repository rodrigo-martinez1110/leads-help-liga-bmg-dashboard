from __future__ import annotations

import io
import math
import re
import zipfile
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping

import pandas as pd


ALL_ORIGINS = "Todas"
UNKNOWN_ORIGIN = "Origem não identificada"
LEAD_COLUMNS = {"Lead.cpf", "Lead.criadoEm", "Lead.numeroWhatsappOrigem"}
PRODUCTION_COLUMNS = {"do_cpf_cliente", "dt_contrato", "ic_producao"}
SENSITIVE_COLUMNS = {
    "cpf_normalizado",
    "do_cpf_cliente",
    "Lead.cpf",
    "nu_contrato",
    "nome",
    "Lead.nome",
    "Lead.telefone",
}


class SourceFormatError(ValueError):
    pass


@dataclass(frozen=True)
class DashboardView:
    kpis: dict[str, Any]
    daily: pd.DataFrame
    reasons: pd.DataFrame
    production_by_product: pd.DataFrame
    production_by_region: pd.DataFrame
    production_scope: pd.DataFrame
    origin_summary: pd.DataFrame


@dataclass(frozen=True)
class DashboardData:
    views: dict[str, DashboardView]
    data_quality: dict[str, int]
    period_start: str | None
    period_end: str | None


def _clean_number(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    text = str(value).strip()
    if not text or text.lower() in {"nan", "nat", "none"}:
        return ""
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    if "e" in text.lower():
        try:
            text = format(Decimal(text), "f")
        except InvalidOperation:
            pass
    return re.sub(r"\D", "", text)


def _normalize_cpf(value: Any) -> str | None:
    digits = _clean_number(value)
    if len(digits) == 10:
        digits = digits.zfill(11)
    if len(digits) != 11 or len(set(digits)) == 1:
        return None

    first_check = sum(int(digits[index]) * (10 - index) for index in range(9))
    first_digit = (first_check * 10 % 11) % 10
    if first_digit != int(digits[9]):
        return None

    second_check = sum(int(digits[index]) * (11 - index) for index in range(10))
    second_digit = (second_check * 10 % 11) % 10
    return digits if second_digit == int(digits[10]) else None


def _normalize_phone(value: Any) -> str:
    digits = _clean_number(value)
    if len(digits) in {10, 11}:
        digits = "55" + digits
    return digits


def parse_origin_mapping(text: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        raw_number, label = line.split(":", 1)
        number = _normalize_phone(raw_number)
        label = label.strip()
        if number and label:
            mapping[number] = label
    return mapping


def _read_csv_bytes(raw: bytes, name: str) -> pd.DataFrame:
    errors: list[str] = []
    for encoding in ("utf-8", "latin1"):
        try:
            first_line = raw.decode(encoding).splitlines()[0]
            delimiters = [",", ";", "\t", "|"]
            separator = max(delimiters, key=first_line.count)
            return pd.read_csv(io.BytesIO(raw), dtype=str, encoding=encoding, sep=separator)
        except UnicodeDecodeError as error:
            errors.append(f"{encoding}: {error}")
    raise SourceFormatError(f"Não foi possível ler {name} como CSV: {'; '.join(errors)}")


def _read_path(path: Path) -> list[tuple[str, pd.DataFrame]]:
    suffix = path.suffix.lower()
    if suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            return _read_zip(archive)
    if suffix == ".csv":
        return [(path.name, _read_csv_bytes(path.read_bytes(), path.name))]
    if suffix in {".xlsx", ".xls"}:
        workbook = pd.ExcelFile(path)
        sheets = workbook.sheet_names
        sheet = "in" if "in" in sheets else sheets[0]
        return [(f"{path.name}:{sheet}", pd.read_excel(path, sheet_name=sheet, dtype=str))]
    raise SourceFormatError(f"Formato não suportado: {path.suffix}")


def _read_zip(archive: zipfile.ZipFile) -> list[tuple[str, pd.DataFrame]]:
    frames: list[tuple[str, pd.DataFrame]] = []
    for info in archive.infolist():
        if info.is_dir() or Path(info.filename).suffix.lower() != ".csv":
            continue
        frames.append((info.filename, _read_csv_bytes(archive.read(info), info.filename)))
    return frames


def _read_bytes(raw: bytes, name: str) -> list[tuple[str, pd.DataFrame]]:
    if zipfile.is_zipfile(io.BytesIO(raw)):
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            if "xl/workbook.xml" in archive.namelist():
                workbook = pd.ExcelFile(io.BytesIO(raw))
                sheet = "in" if "in" in workbook.sheet_names else workbook.sheet_names[0]
                return [(f"{name}:{sheet}", pd.read_excel(io.BytesIO(raw), sheet_name=sheet, dtype=str))]
            return _read_zip(archive)
    if name.lower().endswith((".xlsx", ".xls")):
        workbook = pd.ExcelFile(io.BytesIO(raw))
        sheet = "in" if "in" in workbook.sheet_names else workbook.sheet_names[0]
        return [(f"{name}:{sheet}", pd.read_excel(io.BytesIO(raw), sheet_name=sheet, dtype=str))]
    return [(name, _read_csv_bytes(raw, name))]


def _classify_frames(frames: list[tuple[str, pd.DataFrame]]) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    leads = None
    production = None
    missing_details: list[str] = []
    for name, frame in frames:
        columns = set(frame.columns)
        if LEAD_COLUMNS.issubset(columns):
            leads = frame
        elif PRODUCTION_COLUMNS.issubset(columns):
            production = frame
        else:
            missing_details.append(f"{name}: não corresponde a leads nem produção")
    if leads is None:
        raise SourceFormatError(
            "Base de leads não encontrada. Colunas obrigatórias: "
            + ", ".join(sorted(LEAD_COLUMNS))
        )
    return leads, production


def _find_production_frame(frames: list[tuple[str, pd.DataFrame]]) -> pd.DataFrame | None:
    for _, frame in frames:
        if PRODUCTION_COLUMNS.issubset(set(frame.columns)):
            return frame
    return None


def read_sources(
    source: Path | bytes,
    production_source: Path | bytes | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    if isinstance(source, Path):
        frames = _read_path(source)
        source_name = source.name
    else:
        frames = _read_bytes(source, "upload")
        source_name = "upload"

    leads, production = _classify_frames(frames)
    if production is None and production_source is not None:
        extra_frames = (
            _read_path(production_source)
            if isinstance(production_source, Path)
            else _read_bytes(production_source, "production_upload")
        )
        production = _find_production_frame(
            [(f"{source_name}:{name}", frame) for name, frame in extra_frames]
        )
        if production is None:
            raise SourceFormatError(
                "Base de produção não encontrada. Colunas obrigatórias: "
                + ", ".join(sorted(PRODUCTION_COLUMNS))
            )
    return leads, production


def _parse_datetime(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce", utc=True)
    return parsed.dt.tz_convert("America/Sao_Paulo").dt.tz_localize(None)


def _parse_local_datetime(series: pd.Series) -> pd.Series:
    """Parse dates from operational reports without shifting date-only values."""
    parsed = pd.to_datetime(series, errors="coerce")
    if getattr(parsed.dt, "tz", None) is not None:
        parsed = parsed.dt.tz_convert("America/Sao_Paulo").dt.tz_localize(None)
    return parsed


def _as_bool(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower().isin({"1", "1.0", "true", "sim", "s"})


def _contract_id(value: Any) -> str | None:
    digits = _clean_number(value)
    return digits if digits and set(digits) != {"0"} else None


def _region_from_uf(value: Any) -> str:
    uf = str(value).strip().upper()
    regions = {
        "Norte": {"AC", "AP", "AM", "PA", "RO", "RR", "TO"},
        "Nordeste": {"AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"},
        "Centro-Oeste": {"DF", "GO", "MT", "MS"},
        "Sudeste": {"ES", "MG", "RJ", "SP"},
        "Sul": {"PR", "RS", "SC"},
    }
    for region, states in regions.items():
        if uf in states:
            return region
    return "Sem informação"


def _empty_production_frame(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def _build_view(
    origin: str,
    leads: pd.DataFrame,
    cohort: pd.DataFrame,
    matched_postlead: pd.DataFrame | None,
    origin_summary: pd.DataFrame,
    production_available: bool,
) -> DashboardView:
    lead_scope = leads if origin == ALL_ORIGINS else leads[leads["_origin"] == origin]
    cohort_scope = cohort if origin == ALL_ORIGINS else cohort[cohort["_origin"] == origin]
    postlead_scope = (
        matched_postlead
        if origin == ALL_ORIGINS or matched_postlead is None
        else matched_postlead[matched_postlead["_origin"] == origin]
    )

    unique_valid = int(cohort_scope["_cpf"].nunique())
    invalid_records = int(lead_scope["_cpf"].isna().sum())
    if not production_available:
        postlead_cpfs = None
        conversion_rate = None
        contracts = None
        released_value = None
        average_ticket = None
        postlead_contracts = pd.DataFrame()
    else:
        postlead_cpfs = int(postlead_scope["_cpf"].nunique()) if postlead_scope is not None else 0
        conversion_rate = postlead_cpfs / unique_valid if unique_valid else 0.0
        postlead_contracts = (
            postlead_scope[postlead_scope["_contract_id"].notna()].drop_duplicates("_contract_id")
            if postlead_scope is not None
            else pd.DataFrame()
        )
        contracts = int(postlead_contracts["_contract_id"].nunique())
        released_value = float(postlead_contracts["_released_value"].sum())
        average_ticket = released_value / contracts if contracts else 0.0

    kpis = {
        "lead_records": int(len(lead_scope)),
        "unique_valid_cpfs": unique_valid,
        "invalid_or_missing_cpf_records": invalid_records,
        "production_postlead_cpfs": postlead_cpfs,
        "conversion_rate": conversion_rate,
        "contracts": contracts,
        "released_value": released_value,
        "average_ticket": average_ticket,
    }

    if not production_available or postlead_contracts.empty:
        product = _empty_production_frame(["produto", "contratos", "valor_liberado"])
        region = _empty_production_frame(["regiao", "contratos", "valor_liberado"])
        scope = _empty_production_frame(["produto", "regiao", "contratos", "valor_liberado"])
    else:
        product = (
            postlead_contracts.groupby("_product", dropna=False)
            .agg(contratos=("_contract_id", "nunique"), valor_liberado=("_released_value", "sum"))
            .reset_index()
            .rename(columns={"_product": "produto"})
        )
        region = (
            postlead_contracts.groupby("_region", dropna=False)
            .agg(contratos=("_contract_id", "nunique"), valor_liberado=("_released_value", "sum"))
            .reset_index()
            .rename(columns={"_region": "regiao"})
        )
        scope = (
            postlead_contracts.groupby(["_product", "_region"], dropna=False)
            .agg(contratos=("_contract_id", "nunique"), valor_liberado=("_released_value", "sum"))
            .reset_index()
            .rename(columns={"_product": "produto", "_region": "regiao"})
        )

    postlead_ids = set(cohort_scope.loc[cohort_scope["_cpf"].isin(
        postlead_scope["_cpf"] if postlead_scope is not None else []
    ), "_cpf"])
    daily = cohort_scope.copy()
    if daily.empty:
        daily_frame = pd.DataFrame(columns=["dia", "leads_cpf_unicos", "cpfs_pos_lead", "taxa_pos_lead"])
    else:
        daily["_has_postlead"] = daily["_cpf"].isin(postlead_ids)
        daily_frame = (
            daily.groupby("_lead_date", dropna=False)
            .agg(leads_cpf_unicos=("_cpf", "nunique"), cpfs_pos_lead=("_has_postlead", "sum"))
            .reset_index()
            .rename(columns={"_lead_date": "data_entrada"})
        )
        daily_frame["taxa_pos_lead"] = daily_frame["cpfs_pos_lead"] / daily_frame["leads_cpf_unicos"].replace(0, 1)

    without_postlead = cohort_scope[~cohort_scope["_cpf"].isin(postlead_ids)]
    if without_postlead.empty:
        reasons = pd.DataFrame(columns=["categoria", "leads"])
    else:
        reasons = (
            without_postlead.assign(_reason=without_postlead["_reason"].fillna("Sem informação"))
            .groupby("_reason")
            .size()
            .reset_index(name="leads")
            .rename(columns={"_reason": "categoria"})
            .sort_values("leads", ascending=False)
        )

    return DashboardView(
        kpis=kpis,
        daily=daily_frame,
        reasons=reasons,
        production_by_product=product,
        production_by_region=region,
        production_scope=scope,
        origin_summary=origin_summary,
    )


def build_dashboard_data(
    leads: pd.DataFrame,
    production: pd.DataFrame | None,
    origin_mapping: Mapping[str, str],
) -> DashboardData:
    missing_lead_columns = LEAD_COLUMNS - set(leads.columns)
    if missing_lead_columns:
        raise SourceFormatError("Colunas de leads ausentes: " + ", ".join(sorted(missing_lead_columns)))

    prepared = leads.copy()
    prepared["_cpf"] = prepared["Lead.cpf"].map(_normalize_cpf)
    prepared["_lead_datetime"] = _parse_datetime(prepared["Lead.criadoEm"])
    prepared["_lead_date"] = prepared["_lead_datetime"].dt.normalize()
    prepared["_origin_phone"] = prepared["Lead.numeroWhatsappOrigem"].map(_normalize_phone)
    prepared["_origin"] = prepared["_origin_phone"].map(origin_mapping)
    missing_origin = prepared["_origin"].isna()
    agenda_origin = prepared.get("Lead.origem", pd.Series(index=prepared.index, dtype=str)).astype(str).str.lower().eq("agenda-mais")
    prepared.loc[missing_origin & agenda_origin, "_origin"] = "agenda-mais"
    prepared["_origin"] = prepared["_origin"].fillna(UNKNOWN_ORIGIN)
    prepared["_reason"] = prepared.get("Lead.motivo", pd.Series(index=prepared.index, dtype=str))
    prepared["_row_order"] = range(len(prepared))

    valid = prepared[prepared["_cpf"].notna()].sort_values(["_lead_datetime", "_row_order"])
    cohort = valid.drop_duplicates("_cpf", keep="first").copy()

    # A pessoa fica atribuída à origem do primeiro lead válido. Isso mantém
    # todos os registros repetidos do mesmo CPF no mesmo segmento e evita que
    # uma nova tentativa de contato altere a origem dos KPIs.
    first_origin_by_cpf = cohort.set_index("_cpf")["_origin"]
    prepared["_origin"] = prepared["_cpf"].map(first_origin_by_cpf).fillna(prepared["_origin"])

    prepared_production = None
    matched_postlead = None
    if production is not None:
        missing_production_columns = PRODUCTION_COLUMNS - set(production.columns)
        if missing_production_columns:
            raise SourceFormatError(
                "Colunas de produção ausentes: " + ", ".join(sorted(missing_production_columns))
            )
        prepared_production = production.copy()
        prepared_production["_cpf"] = prepared_production["do_cpf_cliente"].map(_normalize_cpf)
        prepared_production["_contract_date"] = _parse_local_datetime(
            prepared_production["dt_contrato"]
        ).dt.normalize()
        prepared_production["_is_production"] = _as_bool(prepared_production["ic_producao"])
        contract_column = prepared_production.get("nu_contrato", pd.Series(index=prepared_production.index, dtype=str))
        prepared_production["_contract_id"] = contract_column.map(_contract_id)
        released_column = prepared_production.get("vl_liberado", pd.Series(0, index=prepared_production.index))
        prepared_production["_released_value"] = pd.to_numeric(released_column, errors="coerce").fillna(0.0)
        product_column = prepared_production.get("no_produto", pd.Series("Sem informação", index=prepared_production.index))
        prepared_production["_product"] = product_column.fillna("Sem informação").replace("", "Sem informação")
        uf_column = prepared_production.get("no_cliente_uf", pd.Series("", index=prepared_production.index))
        prepared_production["_region"] = uf_column.map(_region_from_uf)
        effective = prepared_production[
            prepared_production["_is_production"] & prepared_production["_cpf"].notna()
        ]
        matched = effective.merge(
            cohort[["_cpf", "_origin", "_lead_date"]],
            on="_cpf",
            how="inner",
        )
        matched_postlead = matched[matched["_contract_date"] >= matched["_lead_date"]].copy()

    origin_labels = sorted(prepared["_origin"].dropna().unique().tolist())
    summary_rows: list[dict[str, Any]] = []
    for origin in origin_labels:
        origin_leads = prepared[prepared["_origin"] == origin]
        origin_cohort = cohort[cohort["_origin"] == origin]
        origin_production = (
            matched_postlead[matched_postlead["_origin"] == origin]
            if matched_postlead is not None
            else None
        )
        origin_contracts = (
            origin_production[origin_production["_contract_id"].notna()].drop_duplicates("_contract_id")
            if origin_production is not None
            else pd.DataFrame()
        )
        released = float(origin_contracts["_released_value"].sum()) if not origin_contracts.empty else None
        contracts = int(origin_contracts["_contract_id"].nunique()) if not origin_contracts.empty else None
        postlead_cpfs = int(origin_production["_cpf"].nunique()) if origin_production is not None else None
        summary_rows.append(
            {
                "origem": origin,
                "leads": int(len(origin_leads)),
                "cpfs_utilizaveis": int(origin_cohort["_cpf"].nunique()),
                "cpfs_pos_lead": postlead_cpfs,
                "taxa_pos_lead": (
                    postlead_cpfs / origin_cohort["_cpf"].nunique()
                    if postlead_cpfs is not None and origin_cohort["_cpf"].nunique()
                    else None
                ),
                "contratos": contracts,
                "valor_liberado": released,
                "ticket_medio": released / contracts if released is not None and contracts else None,
            }
        )

    origin_summary = pd.DataFrame(summary_rows)
    views: dict[str, DashboardView] = {}
    for origin in [ALL_ORIGINS, *origin_labels]:
        selected_summary = origin_summary if origin == ALL_ORIGINS else origin_summary[origin_summary["origem"] == origin]
        views[origin] = _build_view(
            origin,
            prepared,
            cohort,
            matched_postlead,
            selected_summary.reset_index(drop=True),
            production is not None,
        )

    lead_dates = prepared["_lead_date"].dropna()
    data_quality = {
        "lead_records": int(len(prepared)),
        "unique_valid_cpfs": int(cohort["_cpf"].nunique()),
        "invalid_or_missing_cpf_records": int(prepared["_cpf"].isna().sum()),
        "unmapped_origin_records": int((prepared["_origin"] == UNKNOWN_ORIGIN).sum()),
    }
    return DashboardData(
        views=views,
        data_quality=data_quality,
        period_start=lead_dates.min().date().isoformat() if not lead_dates.empty else None,
        period_end=lead_dates.max().date().isoformat() if not lead_dates.empty else None,
    )


def select_view(data: DashboardData, origin: str) -> DashboardView:
    if origin not in data.views:
        raise KeyError(f"Origem não disponível: {origin}")
    return data.views[origin]
