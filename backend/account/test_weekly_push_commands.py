"""存储流（UserWeeklyReport）下的周报管理命令测试。

覆盖三个此前被旧 bucket 版测试 @skip 后失去覆盖的命令：
- send_weekly_push：从每个用户最近一条 UserWeeklyReport 发送邮件；
- retry_failed_weekly_push：重发 status=failed 的 PushRecord；
- generate_user_weekly_reports：批量生成/刷新 UserWeeklyReport。

发送动作统一通过 mock send_weekly_push_email_from_digest 拦截，避免真正发邮件。
"""

from datetime import date, timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from account.models import PushRecord, User, UserWeeklyReport
from account.services.user_weekly_report import build_period_key_from_week_start


SEND_TARGET = (
    "account.management.commands.send_weekly_push.send_weekly_push_email_from_digest"
)


def _sent_result(total=1):
    return {
        "sent": True,
        "sentCount": 1,
        "errorMessage": "",
        "skipped": False,
        "skipReason": "",
        "digest": {"totalPaperCount": total},
        "email": {"subject": "s", "body": "b"},
    }


def _skipped_result():
    return {
        "sent": False,
        "sentCount": 0,
        "errorMessage": "",
        "skipped": True,
        "skipReason": "no_personal_updates",
        "digest": {"totalPaperCount": 0},
        "email": {"subject": "", "body": ""},
    }


def _failed_result(message="smtp timeout"):
    return {
        "sent": False,
        "sentCount": 0,
        "errorMessage": message,
        "skipped": False,
        "skipReason": "",
        "digest": {"totalPaperCount": 0},
        "email": {"subject": "", "body": ""},
    }


class WeeklyPushStorageCommandTestBase(TestCase):
    def setUp(self):
        self.week_start = date(2026, 5, 18)
        self.week_end = date(2026, 5, 24)
        self.user = User.objects.create_user(
            username="weekly_user",
            email="weekly_user@example.com",
            password="abc12345",
            role=User.ROLE_STUDENT,
        )

    def make_report(self, user=None, week_start=None, has_updates=True, total=2):
        user = user or self.user
        week_start = week_start or self.week_start
        return UserWeeklyReport.objects.create(
            user=user,
            week_start=week_start,
            week_end=week_start + timedelta(days=6),
            title=f"专属周报（{week_start.isoformat()}）",
            payload={},
            digest={"hasUpdates": has_updates, "totalPaperCount": total},
            has_updates=has_updates,
            total_paper_count=total,
        )

    def period_key(self, week_start=None):
        return build_period_key_from_week_start(week_start or self.week_start)


class SendWeeklyPushCommandTests(WeeklyPushStorageCommandTestBase):
    def run_command(self, *args):
        out = StringIO()
        call_command("send_weekly_push", *args, stdout=out)
        return out.getvalue()

    def test_warns_when_no_target_users(self):
        # email 为空的用户被 _get_target_users 排除；指定不存在的用户名 -> 无目标。
        output = self.run_command("--user", "ghost_user")
        self.assertIn("No target users found.", output)

    def test_skips_user_without_stored_report(self):
        output = self.run_command("--user", "weekly_user")
        self.assertIn("no stored weekly report yet", output)
        self.assertIn("skipped=1", output)
        self.assertFalse(PushRecord.objects.filter(user=self.user).exists())

    def test_skips_report_without_updates(self):
        self.make_report(has_updates=False, total=0)
        output = self.run_command("--user", "weekly_user")
        self.assertIn("has no personal updates", output)
        self.assertIn("skipped=1", output)

    @patch(SEND_TARGET)
    def test_dry_run_does_not_send_and_returns_early(self, mock_send):
        self.make_report(has_updates=True, total=3)
        output = self.run_command("--user", "weekly_user", "--dry-run")
        mock_send.assert_not_called()
        self.assertIn("[DRY RUN]", output)
        self.assertIn("would send report", output)
        # dry-run 提前 return，不打印发送汇总。
        self.assertNotIn("delivery summary", output)
        self.assertFalse(PushRecord.objects.filter(user=self.user).exists())

    @patch(SEND_TARGET)
    def test_sends_and_marks_push_record_sent(self, mock_send):
        mock_send.return_value = _sent_result(total=2)
        self.make_report(has_updates=True, total=2)

        output = self.run_command("--user", "weekly_user")

        mock_send.assert_called_once()
        record = PushRecord.objects.get(user=self.user, period_key=self.period_key())
        self.assertEqual(record.status, PushRecord.STATUS_SENT)
        self.assertIsNotNone(record.sent_at)
        self.assertEqual(record.error_message, "")
        self.assertIn("weekly_user: sent", output)
        self.assertIn("sent=1", output)

    @patch(SEND_TARGET)
    def test_skips_already_sent_without_force(self, mock_send):
        mock_send.return_value = _sent_result()
        self.make_report(has_updates=True)
        self.run_command("--user", "weekly_user")
        mock_send.reset_mock()

        output = self.run_command("--user", "weekly_user")

        mock_send.assert_not_called()
        self.assertIn("already sent", output)
        self.assertIn("skipped=1", output)

    @patch(SEND_TARGET)
    def test_force_resends_already_sent(self, mock_send):
        mock_send.return_value = _sent_result()
        self.make_report(has_updates=True)
        self.run_command("--user", "weekly_user")
        mock_send.reset_mock()

        output = self.run_command("--user", "weekly_user", "--force")

        mock_send.assert_called_once()
        self.assertIn("weekly_user: sent", output)

    @patch(SEND_TARGET)
    def test_service_skip_result_marks_record_sent(self, mock_send):
        mock_send.return_value = _skipped_result()
        self.make_report(has_updates=True)

        output = self.run_command("--user", "weekly_user")

        record = PushRecord.objects.get(user=self.user, period_key=self.period_key())
        self.assertEqual(record.status, PushRecord.STATUS_SENT)
        self.assertIn("no personal updates", output)
        self.assertIn("skipped=1", output)

    @patch(SEND_TARGET)
    def test_failed_result_marks_record_failed(self, mock_send):
        mock_send.return_value = _failed_result("smtp 550")
        self.make_report(has_updates=True)

        output = self.run_command("--user", "weekly_user")

        record = PushRecord.objects.get(user=self.user, period_key=self.period_key())
        self.assertEqual(record.status, PushRecord.STATUS_FAILED)
        self.assertEqual(record.error_message, "smtp 550")
        self.assertIn("failed=1", output)

    @patch(SEND_TARGET)
    def test_exception_marks_failed_and_is_swallowed_by_handle(self, mock_send):
        mock_send.side_effect = RuntimeError("smtp offline")
        self.make_report(has_updates=True)

        # handle 内部捕获 CommandError，不向外抛出。
        output = self.run_command("--user", "weekly_user")

        record = PushRecord.objects.get(user=self.user, period_key=self.period_key())
        self.assertEqual(record.status, PushRecord.STATUS_FAILED)
        self.assertEqual(record.error_message, "RuntimeError: smtp offline")
        self.assertIn("failure reason: RuntimeError: smtp offline", output)
        self.assertIn("failed=1", output)

    @patch(SEND_TARGET)
    def test_uses_latest_report_when_multiple_weeks_exist(self, mock_send):
        mock_send.return_value = _sent_result()
        self.make_report(week_start=date(2026, 5, 11), has_updates=True)
        latest = self.make_report(week_start=date(2026, 5, 18), has_updates=True)

        self.run_command("--user", "weekly_user")

        expected_key = build_period_key_from_week_start(latest.week_start)
        self.assertTrue(
            PushRecord.objects.filter(user=self.user, period_key=expected_key).exists()
        )


class RetryFailedWeeklyPushCommandTests(WeeklyPushStorageCommandTestBase):
    def make_failed_record(self, user=None, week_start=None):
        user = user or self.user
        week_start = week_start or self.week_start
        return PushRecord.objects.create(
            user=user,
            type=PushRecord.TYPE_WEEKLY,
            period_key=self.period_key(week_start),
            period_start="2026-05-18T00:00:00+08:00",
            period_end="2026-05-24T23:59:59+08:00",
            status=PushRecord.STATUS_FAILED,
            error_message="previous failure",
        )

    def run_command(self, *args):
        out = StringIO()
        call_command("retry_failed_weekly_push", *args, stdout=out)
        return out.getvalue()

    def test_warns_when_no_failed_records(self):
        output = self.run_command()
        self.assertIn("No failed weekly push records found", output)

    def test_dry_run_lists_failed_users(self):
        self.make_failed_record()
        output = self.run_command("--dry-run")
        self.assertIn("[DRY RUN]", output)
        self.assertIn("weekly_user", output)
        # dry-run 不应改变记录状态。
        self.assertEqual(
            PushRecord.objects.get(user=self.user).status, PushRecord.STATUS_FAILED
        )

    def test_period_key_filter_excludes_other_periods(self):
        self.make_failed_record(week_start=date(2026, 5, 18))
        output = self.run_command("--period-key", self.period_key(date(2026, 5, 4)))
        self.assertIn("No failed weekly push records found", output)

    @patch(SEND_TARGET)
    def test_skips_retry_when_no_stored_report(self, mock_send):
        self.make_failed_record()
        # 没有 UserWeeklyReport -> 跳过该用户；之后仍有 failed 记录 -> CommandError。
        with self.assertRaises(CommandError):
            self.run_command()
        mock_send.assert_not_called()

    @patch(SEND_TARGET)
    def test_successful_retry_clears_failed_record(self, mock_send):
        mock_send.return_value = _sent_result()
        self.make_report(has_updates=True)
        self.make_failed_record()

        output = self.run_command()

        record = PushRecord.objects.get(user=self.user)
        self.assertEqual(record.status, PushRecord.STATUS_SENT)
        self.assertIn("Retried 1 failed weekly push user(s).", output)

    @patch(SEND_TARGET)
    def test_still_failed_after_retry_raises(self, mock_send):
        mock_send.return_value = _failed_result("still broken")
        self.make_report(has_updates=True)
        self.make_failed_record()

        with self.assertRaises(CommandError):
            self.run_command()

        record = PushRecord.objects.get(user=self.user)
        self.assertEqual(record.status, PushRecord.STATUS_FAILED)


class GenerateUserWeeklyReportsCommandTests(WeeklyPushStorageCommandTestBase):
    def run_command(self, *args):
        out = StringIO()
        call_command("generate_user_weekly_reports", *args, stdout=out)
        return out.getvalue()

    def test_warns_when_no_target_users(self):
        output = self.run_command("--user", "ghost_user")
        self.assertIn("No target users found.", output)

    def test_generates_empty_report_for_user_without_follows(self):
        # 没有任何关注/私有导师/板块的用户 -> digest 无命中 -> has_updates False。
        # 走真实 service，顺带覆盖 user_weekly_report 生成路径。
        output = self.run_command("--user", "weekly_user")

        report = UserWeeklyReport.objects.get(user=self.user)
        self.assertFalse(report.has_updates)
        self.assertEqual(report.total_paper_count, 0)
        self.assertEqual(
            report.generated_by_kind, UserWeeklyReport.GENERATED_BY_SCHEDULED
        )
        self.assertIn("no updates", output)
        self.assertIn("empty=1", output)

    @patch("account.management.commands.generate_user_weekly_reports.generate_user_weekly_report")
    def test_counts_updates_vs_empty(self, mock_generate):
        other = User.objects.create_user(
            username="weekly_user_2",
            email="weekly_user_2@example.com",
            password="abc12345",
            role=User.ROLE_STUDENT,
        )

        def fake_generate(user, week_offset=0, generated_by_kind=None):
            has_updates = user.username == "weekly_user"
            return UserWeeklyReport.objects.create(
                user=user,
                week_start=self.week_start,
                week_end=self.week_end,
                title="t",
                payload={},
                digest={},
                has_updates=has_updates,
                total_paper_count=5 if has_updates else 0,
                generated_by_kind=generated_by_kind
                or UserWeeklyReport.GENERATED_BY_SCHEDULED,
            )

        mock_generate.side_effect = fake_generate

        output = self.run_command()

        self.assertEqual(mock_generate.call_count, 2)
        # 一个有更新、一个无更新 -> empty=1。
        self.assertIn("total=2", output)
        self.assertIn("empty=1", output)

    @patch("account.management.commands.generate_user_weekly_reports.generate_user_weekly_report")
    def test_passes_week_offset_to_service(self, mock_generate):
        def fake_generate(user, week_offset=0, generated_by_kind=None):
            return UserWeeklyReport.objects.create(
                user=user,
                week_start=self.week_start,
                week_end=self.week_end,
                title="t",
                payload={},
                digest={},
                has_updates=False,
                total_paper_count=0,
                generated_by_kind=UserWeeklyReport.GENERATED_BY_SCHEDULED,
            )

        mock_generate.side_effect = fake_generate

        self.run_command("--user", "weekly_user", "--week-offset", "2")

        self.assertEqual(mock_generate.call_args.kwargs["week_offset"], 2)
