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
    st.error(f"Não foi possível carregar o agregado público: {error}")
    st.stop()

available_origins = list(dashboard.views)
selected_origin = st.sidebar.selectbox("Origem do lead", available_origins, index=0)
view = select_view(dashboard, selected_origin)

scope = view.production_scope.copy()
product_options = sorted(scope["produto"].dropna().unique().tolist()) if not scope.empty else []
region_options = sorted(scope["regiao"].dropna().unique().tolist()) if not scope.empty else []
selected_product = st.sidebar.selectbox("Produto", ["Todos", *product_options])
selected_region = st.sidebar.selectbox("Região do cliente", ["Todas", *region_options])
st.sidebar.caption("Origem recalcula a coorte inteira. Produto e região recalculam os indicadores financeiros.")

if selected_product != "Todos":
    scope = scope[scope["produto"] == selected_product]
if selected_region != "Todas":
    scope = scope[scope["regiao"] == selected_region]

contracts = int(scope["contratos"].sum()) if not scope.empty else 0
released = float(scope["valor_liberado"].sum()) if not scope.empty else 0.0
ticket = released / contracts if contracts else 0.0
kpis = view.kpis

k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Leads no relatório", _fmt_int(kpis["lead_records"]))
k2.metric("CPFs utilizáveis", _fmt_int(kpis["unique_valid_cpfs"]))
k3.metric("Produção pós-lead", _fmt_int(kpis["production_postlead_cpfs"]), _fmt_pct(kpis["conversion_rate"]))
k4.metric("Contratos", _fmt_int(contracts))
k5.metric("Valor liberado", _fmt_brl(released) if kpis["contracts"] is not None else "n/d")
k6.metric("Ticket médio", _fmt_brl(ticket) if kpis["contracts"] is not None else "n/d")

st.info(
    f"Período dos leads: {dashboard.period_start or 'n/d'} a {dashboard.period_end or 'n/d'}. "
    f"Origem selecionada: {selected_origin}. "
    "A associação de produção é temporal por CPF, no mesmo dia ou depois da entrada do lead."
)

st.subheader("Distribuição por origem")
origin_chart = dashboard.views[ALL_ORIGINS].origin_summary.copy()
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
daily = view.daily.copy()
if not daily.empty:
    daily["data"] = pd.to_datetime(daily["data_entrada"]).dt.strftime("%d/%m")
    daily["taxa_pct"] = daily["taxa_pos_lead"] * 100
    fig = px.line(daily, x="data", y="taxa_pct", markers=True, text=daily["taxa_pct"].map(lambda value: f"{value:.1f}%"), color_discrete_sequence=[ORANGE], labels={"data": "Data de entrada", "taxa_pct": "Taxa pós-lead (%)"})
    fig.update_traces(hovertemplate="%{x}<br>%{y:.1f}% pós-lead<extra></extra>")
    fig.update_layout(showlegend=False, height=380, yaxis_ticksuffix="%")
    st.plotly_chart(fig, width="stretch")
else:
    _plot_or_empty(daily, "Sem datas válidas de entrada.")

st.subheader("Motivos entre CPFs sem produção pós-lead")
reasons = view.reasons.head(10).sort_values("leads")
if not reasons.empty:
    fig = px.bar(reasons, x="leads", y="categoria", orientation="h", text="leads", color_discrete_sequence=[TEAL], labels={"leads": "CPFs únicos", "categoria": "Motivo"})
    fig.update_layout(showlegend=False, height=max(360, 34 * len(reasons) + 100))
    st.plotly_chart(fig, width="stretch")
else:
    _plot_or_empty(reasons, "Sem motivos disponíveis.")

with st.expander("Qualidade da base"):
    quality = pd.DataFrame(
        [
            {"Indicador": "Registros de lead", "Quantidade": dashboard.data_quality["lead_records"]},
            {"Indicador": "CPFs válidos distintos", "Quantidade": dashboard.data_quality["unique_valid_cpfs"]},
            {"Indicador": "Registros sem CPF válido", "Quantidade": dashboard.data_quality["invalid_or_missing_cpf_records"]},
            {"Indicador": "Registros sem origem mapeada", "Quantidade": dashboard.data_quality["unmapped_origin_records"]},
        ]
    )
    st.dataframe(quality, hide_index=True, width="stretch")

st.caption("Nenhuma linha individual, CPF, contrato, nome ou telefone é carregado ou exibido pelo painel hospedado. O JSON contém apenas indicadores agregados.")
