"""Tests for Europe/Kyiv winter/summer DST schedule gate."""

from datetime import datetime, timezone

from ksu_news_monitor.config import (
    SUMMER_CRON,
    WINTER_CRON,
    expected_kyiv_cron,
    is_scheduled_kyiv_run_due,
)


def test_winter_eet_uses_0730_utc():
    # November 20, 2026: Ukraine is on winter time (EET, UTC+2)
    winter_dt = datetime(2026, 11, 20, 7, 30, tzinfo=timezone.utc)
    assert expected_kyiv_cron(winter_dt) == WINTER_CRON

    due_winter, _ = is_scheduled_kyiv_run_due("schedule", WINTER_CRON, winter_dt)
    due_summer, _ = is_scheduled_kyiv_run_due("schedule", SUMMER_CRON, winter_dt)
    assert due_winter is True
    assert due_summer is False


def test_summer_eest_uses_0630_utc():
    # July 15, 2026: Ukraine is on summer time (EEST, UTC+3)
    summer_dt = datetime(2026, 7, 15, 6, 30, tzinfo=timezone.utc)
    assert expected_kyiv_cron(summer_dt) == SUMMER_CRON

    due_summer, _ = is_scheduled_kyiv_run_due("schedule", SUMMER_CRON, summer_dt)
    due_winter, _ = is_scheduled_kyiv_run_due("schedule", WINTER_CRON, summer_dt)
    assert due_summer is True
    assert due_winter is False


def test_delayed_github_actions_runner_still_passes_matching_cron():
    # GitHub Actions sometimes starts 06:30 UTC cron at 07:08 UTC
    delayed_summer = datetime(2026, 7, 15, 7, 8, tzinfo=timezone.utc)
    due, _ = is_scheduled_kyiv_run_due("schedule", SUMMER_CRON, delayed_summer)
    assert due is True


def test_workflow_dispatch_always_runs():
    winter_dt = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
    due, _ = is_scheduled_kyiv_run_due("workflow_dispatch", "", winter_dt)
    assert due is True
