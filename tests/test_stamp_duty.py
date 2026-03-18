"""Unit tests for stamp duty calculator — pure math, no network."""

import pytest

from property_core.stamp_duty import calculate_stamp_duty


class TestStandardPurchase:
    """Standard rates (not additional property, not FTB)."""

    def test_300k(self):
        r = calculate_stamp_duty(300_000, additional_property=False)
        # 0% on 0-125k = 0, 2% on 125k-250k = 2500, 5% on 250k-300k = 2500
        assert r.total_sdlt == 5_000
        assert r.additional_property is False
        assert len(r.breakdown) == 3

    def test_500k(self):
        r = calculate_stamp_duty(500_000, additional_property=False)
        # 0 + 2500 + 12500 = 15000
        assert r.total_sdlt == 15_000

    def test_1m(self):
        r = calculate_stamp_duty(1_000_000, additional_property=False)
        # 0 + 2500 + 33750 + 7500 = 43750
        assert r.total_sdlt == 43_750

    def test_2m(self):
        r = calculate_stamp_duty(2_000_000, additional_property=False)
        # 0 + 2500 + 33750 + 57500 + 60000 = 153750
        assert r.total_sdlt == 153_750


class TestAdditionalProperty:
    """Additional property surcharge (+5% on every band)."""

    def test_300k_additional(self):
        r = calculate_stamp_duty(300_000, additional_property=True)
        # 5% on 0-125k = 6250, 7% on 125k-250k = 8750, 10% on 250k-300k = 5000
        assert r.total_sdlt == 20_000
        assert r.surcharges_applied == 5

    def test_150k_additional(self):
        r = calculate_stamp_duty(150_000, additional_property=True)
        # 5% on 0-125k = 6250, 7% on 125k-150k = 1750
        assert r.total_sdlt == 8_000


class TestFirstTimeBuyer:
    """FTB relief — 0% up to 300k, 5% on 300k-500k."""

    def test_ftb_300k(self):
        r = calculate_stamp_duty(300_000, additional_property=False, first_time_buyer=True)
        # 0% on entire 300k
        assert r.total_sdlt == 0
        assert len(r.breakdown) == 1
        assert r.breakdown[0].rate == 0

    def test_ftb_400k(self):
        r = calculate_stamp_duty(400_000, additional_property=False, first_time_buyer=True)
        # 0% on 0-300k = 0, 5% on 300k-400k = 5000
        assert r.total_sdlt == 5_000

    def test_ftb_500k(self):
        r = calculate_stamp_duty(500_000, additional_property=False, first_time_buyer=True)
        # 0% on 0-300k = 0, 5% on 300k-500k = 10000
        assert r.total_sdlt == 10_000

    def test_ftb_over_500k_falls_back_to_standard(self):
        """FTB relief doesn't apply if price exceeds 500k."""
        r = calculate_stamp_duty(600_000, additional_property=False, first_time_buyer=True)
        standard = calculate_stamp_duty(600_000, additional_property=False, first_time_buyer=False)
        assert r.total_sdlt == standard.total_sdlt

    def test_ftb_with_additional_uses_standard(self):
        """FTB relief incompatible with additional property surcharge."""
        r = calculate_stamp_duty(300_000, additional_property=True, first_time_buyer=True)
        additional = calculate_stamp_duty(300_000, additional_property=True, first_time_buyer=False)
        assert r.total_sdlt == additional.total_sdlt


class TestNonResident:
    """Non-resident surcharge (+2%)."""

    def test_non_resident_300k(self):
        r = calculate_stamp_duty(300_000, additional_property=False, non_resident=True)
        # 2% on 0-125k = 2500, 4% on 125k-250k = 5000, 7% on 250k-300k = 3500
        assert r.total_sdlt == 11_000
        assert r.surcharges_applied == 2

    def test_non_resident_additional_stacks(self):
        """Both surcharges stack (+7% total)."""
        r = calculate_stamp_duty(300_000, additional_property=True, non_resident=True)
        # 7% on 0-125k = 8750, 9% on 125k-250k = 11250, 12% on 250k-300k = 6000
        assert r.total_sdlt == 26_000
        assert r.surcharges_applied == 7


class TestEdgeCases:

    def test_zero_price(self):
        r = calculate_stamp_duty(0)
        assert r.total_sdlt == 0
        assert r.effective_rate == 0
        assert r.breakdown == []

    def test_one_pound(self):
        r = calculate_stamp_duty(1, additional_property=False)
        assert r.total_sdlt == 0  # 0% band

    def test_negative_price_raises(self):
        with pytest.raises(ValueError, match="negative"):
            calculate_stamp_duty(-1)

    def test_effective_rate(self):
        r = calculate_stamp_duty(300_000, additional_property=False)
        assert r.effective_rate == pytest.approx(1.67, abs=0.01)

    def test_breakdown_amounts_sum_to_price(self):
        r = calculate_stamp_duty(750_000, additional_property=True)
        assert sum(b.amount for b in r.breakdown) == 750_000

    def test_breakdown_taxes_sum_to_total(self):
        r = calculate_stamp_duty(750_000, additional_property=True)
        assert sum(b.tax for b in r.breakdown) == pytest.approx(r.total_sdlt, abs=0.01)
