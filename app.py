from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from data_pipeline import ALL_ORIGINS, select_view
from public_data import PublicDataError, load_dashboard_data


ROOT = Path(__file__).resolve().parent
PUBLIC_DATA_PATH = ROOT / "dashboard_data_public.json"
ORANGE = "#F58220"
TEAL = "#24A6A0"

st.set_page_config(page_title="Leads e produção | help!", page_icon="📊", layout="wide")
st.markdown(
    """
    <style>
      [data-testid="stMetric"] {
        border-top: 3px solid #F58220;
        padding: 12px 16px;
      }
    </style>
    """,
    unsafe_allow_html=True,
)


def _fmt_int(value: int | float | None) -> str:
    return "n/d" if value is None else f"{int(value):,}".replace(",", ".")


def _fmt_brl(value: float | None) -> str:
    if value is None:
        return "n/d"
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_pct(value: float | None) -> str:
    return "n/d" if value is None else f"{value:.1%}"


def _plot_or_empty(frame: pd.DataFrame, message: str) -> None:
    if frame.empty:
        st.caption(message)


st.title("Leads CRM e produção")
st.caption("Painel público com indicadores agregados · dados individuais e mapeamentos privados não são carregados no Streamlit")
try:
    dashboard = load_dashboard_data(PUBLIC_DATA_PATH)
except PublicDataError as error:
    st.error(f"Não foi possível carregar o agregado público: {error}. Gere novamente `dashboard_data_public.json` com a versão atual do gerador de dados.")
    st.stop()

if not dashboard.period_start or not dashboard.period_end:
    st.error("O agregado não tem datas válidas para montar o filtro de período.")
    st.stop()

available_origins = list(dashboard.views)
selected_origin = st.sidebar.selectbox("Origem do lead", available_origins, index=0)
view = select_view(dashboard, selected_origin)

period_start = pd.Timestamp(dashboard.period_start).date()
period_end = pd.Timestamp(dashboard.period_end).date()
selected_period = st.sidebar.date_input(
    "Período dos leads",
    value=(period_start, period_end),
    min_value=period_start,
    max_value=period_end,
    format="DD/MM/YYYY",
)
if not isinstance(selected_period, (tuple, list)) or len(selected_period) != 2 or any(value is None for value in selected_period):
    st.info("Selecione a data inicial e a data final para ver os indicadores do período.")
    st.stop()
selected_start, selected_end = map(pd.Timestamp, selected_period)
if selected_start > selected_end:
    st.error("A data inicial precisa ser anterior ou igual à data final.")
    st.stop()

daily = view.daily.copy()
daily["data_entrada"] = pd.to_datetime(daily["data_entrada"], errors="coerce")
daily = daily[daily["data_entrada"].between(selected_start, selected_end, inclusive="both")]

scope = view.production_scope.copy()
if not scope.empty:
    scope["data_entrada"] = pd.to_datetime(scope["data_entrada"], errors="coerce")
    scope = scope[scope["data_entrada"].between(selected_start, selected_end, inclusive="both")]
product_options = sorted(scope["produto"].dropna().unique().tolist()) if not scope.empty else []
region_options = sorted(scope["regiao"].dropna().unique().tolist()) if not scope.empty else []
selected_product = st.sidebar.selectbox("Produto", ["Todos", *product_options])
selected_region = st.sidebar.selectbox("Região do cliente", ["Todas", *region_options])
st.sidebar.caption("Período e origem atualizam toda a visão. Produto e região filtram a visão financeira.")

if selected_product != "Todos":
    scope = scope[scope["produto"] == selected_product]
if selected_region != "Todas":
    scope = scope[scope["regiao"] == selected_region]

daily_totals = {
    column: int(daily[column].sum()) if not daily.empty else 0
    for column in ["lead_records", "unique_valid_cpfs", "invalid_or_missing_cpf_records", "unmapped_origin_records", "cpfs_pos_lead"]
}
kpis = view.kpis.copy()
kpis["lead_records"] = daily_totals["lead_records"]
kpis["unique_valid_cpfs"] = daily_totals["unique_valid_cpfs"]
kpis["invalid_or_missing_cpf_records"] = daily_totals["invalid_or_missing_cpf_records"]
if view.kpis["production_postlead_cpfs"] is not None:
    kpis["production_postlead_cpfs"] = daily_totals["cpfs_pos_lead"]
    kpis["conversion_rate"] = daily_totals["cpfs_pos_lead"] / max(daily_totals["unique_valid_cpfs"], 1)

financial_available = view.kpis["contracts"] is not None
contracts = int(scope["contratos"].sum()) if financial_available and not scope.empty else (0 if financial_available else None)
released = float(scope["valor_liberado"].sum()) if financial_available and not scope.empty else (0.0 if financial_available else None)
ticket = released / contracts if released is not None and contracts else (0.0 if financial_available else None)

k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric(
    "Leads no relatório",
    _fmt_int(kpis["lead_records"]),
    help="Quantidade de registros de lead no intervalo escolhido, incluindo os que não têm CPF válido.",
)
k2.metric(
    "CPFs utilizáveis",
    _fmt_int(kpis["unique_valid_cpfs"]),
    help="Quantidade de CPFs válidos e únicos no intervalo escolhido.",
)
k3.metric(
    "Produção pós-lead",
    _fmt_int(kpis["production_postlead_cpfs"]),
    _fmt_pct(kpis["conversion_rate"]),
    help="CPFs únicos com produção no mesmo dia ou após o primeiro lead. Associação temporal não prova causalidade.",
)
k4.metric(
    "Contratos",
    _fmt_int(contracts),
    help="Total de contratos dentro do intervalo e dos filtros de origem, produto e região.",
)
k5.metric(
    "Valor liberado",
    _fmt_brl(released),
    help="Soma do valor liberado nos contratos considerados pelos filtros selecionados.",
)
k6.metric(
    "Ticket médio",
    _fmt_brl(ticket),
    help="Valor liberado dividido pela quantidade de contratos considerados pelos filtros selecionados.",
)

st.info(
    f"Período selecionado: {selected_start:%d/%m/%Y} a {selected_end:%d/%m/%Y}. "
    f"Origem selecionada: {selected_origin}. "
    "A associação de produção é temporal por CPF, no mesmo dia ou depois da entrada do lead."
)

st.subheader("Distribuição por origem")
origin_chart = dashboard.views[ALL_ORIGINS].origin_summary.copy()
if not origin_chart.empty:
    origin_chart["data_entrada"] = pd.to_datetime(origin_chart["data_entrada"], errors="coerce")
    origin_chart = origin_chart[origin_chart["data_entrada"].between(selected_start, selected_end, inclusive="both")]
    origin_chart = origin_chart.groupby("origem", as_index=False).agg(leads=("leads", "sum"))
if not origin_chart.empty:
    fig = px.bar(origin_chart.sort_values("leads"), x="leads", y="origem", orientation="h", text="leads", color_discrete_sequence=[ORANGE], labels={"leads": "Registros de lead", "origem": "Origem"})
    fig.update_layout(showlegend=False, height=max(320, 36 * len(origin_chart) + 100))
    st.plotly_chart(fig, width="stretch")
else:
    _plot_or_empty(origin_chart, "Sem dados de origem para os filtros selecionados.")

left, right = st.columns(2)
with left:
    st.subheader("Contratos por produto")
    by_product = (
        scope.groupby("produto", as_index=False).agg(contratos=("contratos", "sum"), valor_liberado=("valor_liberado", "sum"))
        if not scope.empty
        else pd.DataFrame(columns=["produto", "contratos", "valor_liberado"])
    )
    if not by_product.empty:
        fig = px.bar(by_product.sort_values("contratos"), x="contratos", y="produto", orientation="h", text="contratos", color_discrete_sequence=[ORANGE])
        fig.update_layout(showlegend=False, height=max(320, 36 * len(by_product) + 100))
        st.plotly_chart(fig, width="stretch")
    else:
        _plot_or_empty(by_product, "Sem contratos para os filtros selecionados.")

with right:
    st.subheader("Contratos por região")
    by_region = (
        scope.groupby("regiao", as_index=False).agg(contratos=("contratos", "sum"), valor_liberado=("valor_liberado", "sum"))
        if not scope.empty
        else pd.DataFrame(columns=["regiao", "contratos", "valor_liberado"])
    )
    if not by_region.empty:
        fig = px.bar(by_region.sort_values("contratos"), x="contratos", y="regiao", orientation="h", text="contratos", color_discrete_sequence=[TEAL])
        fig.update_layout(showlegend=False, height=max(320, 36 * len(by_region) + 100))
        st.plotly_chart(fig, width="stretch")
    else:
        _plot_or_empty(by_region, "Sem contratos para os filtros selecionados.")

st.subheader("Produção pós-lead por dia de entrada")
if not daily.empty:
    daily["taxa_pct"] = daily["taxa_pos_lead"] * 100
    range_days = int((selected_end - selected_start).days)
    if range_days <= 14:
        tick_step = 24 * 60 * 60 * 1000
        tick_angle = -35
    elif range_days <= 60:
        tick_step = 7 * 24 * 60 * 60 * 1000
        tick_angle = 0
    elif range_days <= 180:
        tick_step = 14 * 24 * 60 * 60 * 1000
        tick_angle = 0
    else:
        tick_step = "M1"
        tick_angle = 0
    point_text = daily["taxa_pct"].map(lambda value: f"{value:.1f}%") if range_days <= 14 else None
    fig = px.line(daily, x="data_entrada", y="taxa_pct", markers=True, text=point_text, color_discrete_sequence=[ORANGE], labels={"data_entrada": "Data de entrada", "taxa_pct": "Taxa pós-lead (%)"})
    fig.update_traces(hovertemplate="%{x|%d/%m/%Y}<br>%{y:.1f}% pós-lead<extra></extra>")
    fig.update_xaxes(type="date", tickformat="%d/%m", dtick=tick_step, tick0=selected_start.isoformat(), tickangle=tick_angle)
    fig.update_layout(showlegend=False, height=380, yaxis_ticksuffix="%")
    st.plotly_chart(fig, width="stretch")
else:
    _plot_or_empty(daily, "Sem datas válidas de entrada.")

st.subheader("Motivos entre CPFs sem produção pós-lead")
reasons = view.reasons.copy()
if not reasons.empty:
    reasons["data_entrada"] = pd.to_datetime(reasons["data_entrada"], errors="coerce")
    reasons = reasons[reasons["data_entrada"].between(selected_start, selected_end, inclusive="both")]
    reasons = reasons.groupby("categoria", as_index=False).agg(leads=("leads", "sum")).nlargest(10, "leads").sort_values("leads")
if not reasons.empty:
    fig = px.bar(reasons, x="leads", y="categoria", orientation="h", text="leads", color_discrete_sequence=[TEAL], labels={"leads": "CPFs únicos", "categoria": "Motivo"})
    fig.update_layout(showlegend=False, height=max(360, 34 * len(reasons) + 100))
    st.plotly_chart(fig, width="stretch")
else:
    _plot_or_empty(reasons, "Sem motivos disponíveis.")

with st.expander("Qualidade da base"):
    quality_daily = dashboard.views[ALL_ORIGINS].daily.copy()
    quality_daily["data_entrada"] = pd.to_datetime(quality_daily["data_entrada"], errors="coerce")
    quality_daily = quality_daily[quality_daily["data_entrada"].between(selected_start, selected_end, inclusive="both")]
    quality = {column: int(quality_daily[column].sum()) if not quality_daily.empty else 0 for column in ["lead_records", "unique_valid_cpfs", "invalid_or_missing_cpf_records", "unmapped_origin_records"]}
    quality = pd.DataFrame(
        [
            {"Indicador": "Registros de lead", "Quantidade": quality["lead_records"]},
            {"Indicador": "CPFs válidos distintos", "Quantidade": quality["unique_valid_cpfs"]},
            {"Indicador": "Registros sem CPF válido", "Quantidade": quality["invalid_or_missing_cpf_records"]},
            {"Indicador": "Registros sem origem mapeada", "Quantidade": quality["unmapped_origin_records"]},
        ]
    )
    st.dataframe(quality, hide_index=True, width="stretch")

st.caption("Nenhuma linha individual, CPF, contrato, nome ou telefone é carregado ou exibido pelo painel hospedado. O JSON contém apenas indicadores agregados.")
