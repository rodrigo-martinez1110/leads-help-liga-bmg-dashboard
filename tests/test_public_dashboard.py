from __future__ import annotations

import pandas as pd
import pytest

from data_pipeline import DashboardData, DashboardView
from public_data import PublicDataError, deserialize_dashboard_data, serialize_dashboard_data


def _dashboard() -> DashboardData:
    view = DashboardView(
        kpis={
            "lead_records": 2,
            "unique_valid_cpfs": 1,
            "invalid_or_missing_cpf_records": 0,
            "production_postlead_cpfs": 1,
            "conversion_rate": 1.0,
            "contracts": 1,
            "released_value": 1000.0,
            "average_ticket": 1000.0,
        },
        daily=pd.DataFrame([{"data_entrada": "2026-10-05", "leads_cpf_unicos": 1, "cpfs_pos_lead": 1, "taxa_pos_lead": 1.0}]),
        reasons=pd.DataFrame(columns=["categoria", "leads"]),
        production_by_product=pd.DataFrame(columns=["produto", "contratos", "valor_liberado"]),
        production_by_region=pd.DataFrame(columns=["regiao", "contratos", "valor_liberado"]),
        production_scope=pd.DataFrame(columns=["produto", "regiao", "contratos", "valor_liberado"]),
        origin_summary=pd.DataFrame(columns=["origem", "leads", "cpfs_utilizaveis", "cpfs_pos_lead", "taxa_pos_lead", "contratos", "valor_liberado", "ticket_medio"]),
    )
    return DashboardData(
        views={"Todas": view, "Site": view},
        data_quality={"lead_records": 2, "unique_valid_cpfs": 1, "invalid_or_missing_cpf_records": 0, "unmapped_origin_records": 0},
        period_start="2026-10-05",
        period_end="2026-10-09",
    )


def test_public_dashboard_round_trip_contains_only_aggregate_schema():
    payload = serialize_dashboard_data(_dashboard())

    assert set(payload) == {"schema_version", "period_start", "period_end", "data_quality", "views"}
    assert "cpf_normalizado" not in str(payload)
    assert "telefone" not in str(payload).lower()
    restored = deserialize_dashboard_data(payload)
    assert restored.views["Site"].kpis["lead_records"] == 2
    assert restored.views["Site"].daily.iloc[0]["cpfs_pos_lead"] == 1


def test_public_dashboard_rejects_unapproved_record_fields():
    payload = serialize_dashboard_data(_dashboard())
    payload["views"]["Site"]["daily"][0]["cpf_normalizado"] = "12345678901"

    with pytest.raises(PublicDataError):
        deserialize_dashboard_data(payload)
