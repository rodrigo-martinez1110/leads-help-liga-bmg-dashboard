import tempfile
import unittest
from pathlib import Path

import pandas as pd

from data_pipeline import build_dashboard_data, parse_origin_mapping, read_sources, select_view


FIXTURES = Path(__file__).parent / "fixtures"
MAPPING = "0000000001: CRM\n0000000002: site"


def _valid_test_cpf(seed: str) -> str:
    digits = [int(digit) for digit in seed]
    first = sum(digits[index] * (10 - index) for index in range(9))
    first_digit = (first * 10 % 11) % 10
    digits.append(first_digit)
    second = sum(digits[index] * (11 - index) for index in range(10))
    second_digit = (second * 10 % 11) % 10
    return "".join(map(str, [*digits, second_digit]))


def _load_week(name: str, cpf_tokens: dict[str, str]):
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        paths = []
        for kind in ("leads", "production"):
            source = FIXTURES / f"{name}_{kind}.csv"
            frame = pd.read_csv(source, dtype=str)
            for token, cpf in cpf_tokens.items():
                frame = frame.replace(token, cpf)
            path = folder / source.name
            frame.to_csv(path, index=False)
            paths.append(path)
        leads, production = read_sources(paths[0], paths[1])
        return build_dashboard_data(leads, production, parse_origin_mapping(MAPPING))


class WeeklyRefreshTests(unittest.TestCase):
    def test_new_week_replaces_period_origins_and_metrics(self):
        week_a = _load_week("week_a", {"CPF_A": _valid_test_cpf("101010101")})
        week_b = _load_week(
            "week_b",
            {
                "CPF_B": _valid_test_cpf("202020202"),
                "CPF_C": _valid_test_cpf("303030303"),
            },
        )

        crm = select_view(week_a, "CRM")
        site = select_view(week_b, "site")
        self.assertEqual((week_a.period_start, week_a.period_end), ("2026-10-05", "2026-10-05"))
        self.assertEqual((week_b.period_start, week_b.period_end), ("2026-10-12", "2026-10-13"))
        self.assertEqual(set(week_a.views), {"Todas", "CRM"})
        self.assertEqual(set(week_b.views), {"Todas", "site"})
        self.assertEqual(crm.kpis["lead_records"], 1)
        self.assertEqual(crm.kpis["production_postlead_cpfs"], 1)
        self.assertEqual(site.kpis["lead_records"], 2)
        self.assertEqual(site.kpis["production_postlead_cpfs"], 0)
        self.assertAlmostEqual(crm.kpis["conversion_rate"], 1.0)
        self.assertAlmostEqual(site.kpis["conversion_rate"], 0.0)


if __name__ == "__main__":
    unittest.main()
