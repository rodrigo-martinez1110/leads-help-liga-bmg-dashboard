import io
import tempfile
import unittest
import zipfile
from pathlib import Path

import pandas as pd

from data_pipeline import (
    build_dashboard_data,
    parse_origin_mapping,
    read_sources,
    select_view,
)


MAPPING_TEXT = """
0000000001: CRM
0000000002: site
0000000003: Redirect
0000000004: Mídia
0000000005: backup
0000000006: backup
"""


def _test_cpf(seed: str) -> str:
    digits = [int(digit) for digit in seed]
    first = sum(digits[index] * (10 - index) for index in range(9))
    digits.append((first * 10 % 11) % 10)
    second = sum(digits[index] * (11 - index) for index in range(10))
    digits.append((second * 10 % 11) % 10)
    return "".join(map(str, digits))


def lead_rows():
    cpf_a, cpf_b, cpf_c = (
        _test_cpf("101010101"),
        _test_cpf("202020202"),
        _test_cpf("303030303"),
    )
    return pd.DataFrame(
        [
            {
                "Lead.cpf": cpf_a,
                "Lead.criadoEm": "2026-10-05T10:00:00Z",
                "Lead.numeroWhatsappOrigem": "0000000001",
                "Lead.origem": "WHATSAPP",
                "Lead.motivo": "Sem interesse",
            },
            {
                "Lead.cpf": cpf_a,
                "Lead.criadoEm": "2026-10-06T10:00:00Z",
                "Lead.numeroWhatsappOrigem": "0000000002",
                "Lead.origem": "WHATSAPP",
                "Lead.motivo": "Duplicado",
            },
            {
                "Lead.cpf": cpf_b,
                "Lead.criadoEm": "2026-10-05T11:00:00Z",
                "Lead.numeroWhatsappOrigem": "0000000002",
                "Lead.origem": "WHATSAPP",
                "Lead.motivo": "Sem oferta",
            },
            {
                "Lead.cpf": None,
                "Lead.criadoEm": "2026-10-05T12:00:00Z",
                "Lead.numeroWhatsappOrigem": None,
                "Lead.origem": "agenda-mais",
                "Lead.motivo": "Sem informação",
            },
            {
                "Lead.cpf": cpf_c,
                "Lead.criadoEm": "2026-10-07T12:00:00Z",
                "Lead.numeroWhatsappOrigem": "0000000007",
                "Lead.origem": "WHATSAPP",
                "Lead.motivo": "Sem informação",
            },
        ]
    )


def production_rows():
    cpf_a, cpf_b, cpf_c = (
        _test_cpf("101010101"),
        _test_cpf("202020202"),
        _test_cpf("303030303"),
    )
    return pd.DataFrame(
        [
            {
                "do_cpf_cliente": cpf_a,
                "dt_contrato": "2026-10-05",
                "ic_producao": 1,
                "nu_contrato": "100",
                "vl_liberado": 100.0,
                "no_produto": "CNC",
                "no_cliente_uf": "SP",
            },
            {
                "do_cpf_cliente": cpf_b,
                "dt_contrato": "2026-10-04",
                "ic_producao": 1,
                "nu_contrato": "101",
                "vl_liberado": 200.0,
                "no_produto": "Consignado",
                "no_cliente_uf": "RJ",
            },
            {
                "do_cpf_cliente": cpf_c,
                "dt_contrato": "2026-10-08",
                "ic_producao": 1,
                "nu_contrato": "102",
                "vl_liberado": 300.0,
                "no_produto": "FGTS",
                "no_cliente_uf": "MG",
            },
        ]
    )


class DataPipelineTests(unittest.TestCase):
    def test_parses_origin_mapping_with_country_prefix_and_duplicate_label(self):
        mapping = parse_origin_mapping(MAPPING_TEXT)

        self.assertEqual(mapping["550000000001"], "CRM")
        self.assertEqual(mapping["550000000002"], "site")
        self.assertEqual(mapping["550000000005"], "backup")
        self.assertEqual(mapping["550000000006"], "backup")

    def test_reads_leads_and_production_from_zip(self):
        lead_csv = lead_rows().to_csv(index=False).encode("utf-8")
        production_csv = production_rows().to_csv(index=False).encode("utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "weekly.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("leads.csv", lead_csv)
                zf.writestr("production.csv", production_csv)

            leads, production = read_sources(archive)

        self.assertEqual(len(leads), 5)
        self.assertEqual(len(production), 3)

    def test_reads_production_from_separate_upload(self):
        with tempfile.TemporaryDirectory() as tmp:
            leads_path = Path(tmp) / "leads.csv"
            leads_path.write_bytes(lead_rows().to_csv(index=False).encode("utf-8"))
            production_bytes = production_rows().to_csv(index=False).encode("utf-8")

            leads, production = read_sources(leads_path, production_bytes)

        self.assertEqual(len(leads), 5)
        self.assertEqual(len(production), 3)

    def test_reads_semicolon_csv_and_quoted_commas(self):
        source = (
            "Lead.cpf;Lead.criadoEm;Lead.numeroWhatsappOrigem;Lead.motivo\n"
            f'{_test_cpf("101010101")};2026-10-05T10:00:00Z;0000000001;"motivo, com vírgula"\n'
        ).encode("utf-8")

        leads, production = read_sources(source)

        self.assertEqual(len(leads), 1)
        self.assertEqual(leads.iloc[0]["Lead.motivo"], "motivo, com vírgula")
        self.assertIsNone(production)

    def test_reads_xlsx_upload_bytes(self):
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            lead_rows().to_excel(writer, sheet_name="in", index=False)

        leads, production = read_sources(buffer.getvalue())

        self.assertEqual(len(leads), 5)
        self.assertIsNone(production)

    def test_builds_origin_specific_kpis_and_assigns_duplicate_cpf_to_first_origin(self):
        data = build_dashboard_data(lead_rows(), production_rows(), parse_origin_mapping(MAPPING_TEXT))

        crm = select_view(data, "CRM")
        site = select_view(data, "site")
        agenda = select_view(data, "agenda-mais")
        all_data = select_view(data, "Todas")

        self.assertEqual(crm.kpis["lead_records"], 2)
        self.assertEqual(crm.kpis["unique_valid_cpfs"], 1)
        self.assertEqual(crm.kpis["production_postlead_cpfs"], 1)
        self.assertEqual(crm.kpis["contracts"], 1)
        self.assertEqual(crm.kpis["released_value"], 100.0)
        self.assertEqual(site.kpis["production_postlead_cpfs"], 0)
        self.assertEqual(agenda.kpis["lead_records"], 1)
        self.assertEqual(all_data.kpis["lead_records"], 5)
        self.assertEqual(all_data.kpis["unique_valid_cpfs"], 3)
        self.assertIn("Origem não identificada", data.views)

    def test_without_production_keeps_lead_kpis_and_marks_production_unavailable(self):
        data = build_dashboard_data(lead_rows(), None, parse_origin_mapping(MAPPING_TEXT))
        view = select_view(data, "CRM")

        self.assertEqual(view.kpis["unique_valid_cpfs"], 1)
        self.assertIsNone(view.kpis["production_postlead_cpfs"])
        self.assertTrue(view.production_by_product.empty)

    def test_output_views_contain_only_aggregate_columns(self):
        data = build_dashboard_data(lead_rows(), production_rows(), parse_origin_mapping(MAPPING_TEXT))
        sensitive_columns = {"cpf_normalizado", "do_cpf_cliente", "Lead.cpf", "nu_contrato", "nome"}

        for view in data.views.values():
            for frame in [
                view.daily,
                view.reasons,
                view.production_by_product,
                view.production_by_region,
                view.production_scope,
                view.origin_summary,
            ]:
                self.assertTrue(sensitive_columns.isdisjoint(frame.columns))


if __name__ == "__main__":
    unittest.main()
