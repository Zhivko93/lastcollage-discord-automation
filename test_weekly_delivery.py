import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch, Mock
import requests
import weekly_lastcollage_to_discord as app


def response(code):
    result = Mock(status_code=code)
    if code >= 400:
        result.raise_for_status.side_effect = requests.HTTPError(str(code))
    return result


class DeliveryTests(unittest.TestCase):
    def test_claim_created(self):
        with patch.object(app, "github_delivery_request", return_value=response(201)), patch.dict(os.environ, {"GITHUB_SHA": "abc"}):
            self.assertTrue(app.claim_delivery(datetime(2026, 10, 11, 18, tzinfo=timezone.utc)))

    def test_existing_claim_skips(self):
        with patch.object(app, "github_delivery_request", side_effect=[response(422), response(200)]), patch.dict(os.environ, {"GITHUB_SHA": "abc"}):
            self.assertFalse(app.claim_delivery(datetime(2026, 10, 11, 18, tzinfo=timezone.utc)))

    def test_permission_failure_does_not_allow_send(self):
        with patch.object(app, "github_delivery_request", return_value=response(403)):
            with self.assertRaises(requests.HTTPError):
                app.delivery_already_claimed(datetime.now(timezone.utc))

    def test_preview_does_not_claim_or_send(self):
        with patch.dict(os.environ, {"LASTFM_USERNAME": "test", "LASTFM_API_KEY": "test", "PREVIEW_ONLY": "true"}), patch.object(app, "lastfm_get_recent_tracks", return_value=[]), patch.object(app, "build_album_records", return_value=[]), patch.object(app, "build_collage"), patch.object(app, "claim_delivery") as claim, patch.object(app, "send_to_discord") as send:
            app.main()
            claim.assert_not_called()
            send.assert_not_called()

    def test_duplicate_run_does_not_generate_or_send(self):
        with patch.dict(os.environ, {"LASTFM_USERNAME": "test", "LASTFM_API_KEY": "test", "DISCORD_WEBHOOK_URL": "test", "PREVIEW_ONLY": "false", "GITHUB_EVENT_NAME": "workflow_dispatch"}), patch.object(app, "delivery_already_claimed", return_value=True), patch.object(app, "lastfm_get_recent_tracks") as fetch, patch.object(app, "send_to_discord") as send:
            app.main()
            fetch.assert_not_called()
            send.assert_not_called()

    def test_racing_claim_prevents_send(self):
        with patch.dict(os.environ, {"LASTFM_USERNAME": "test", "LASTFM_API_KEY": "test", "DISCORD_WEBHOOK_URL": "test", "PREVIEW_ONLY": "false", "GITHUB_EVENT_NAME": "workflow_dispatch"}), patch.object(app, "delivery_already_claimed", return_value=False), patch.object(app, "lastfm_get_recent_tracks", return_value=[]), patch.object(app, "build_album_records", return_value=[]), patch.object(app, "build_collage"), patch.object(app, "claim_delivery", return_value=False), patch.object(app, "send_to_discord") as send:
            app.main()
            send.assert_not_called()

    def test_early_schedule_waits_for_same_week_cutoff(self):
        with patch.dict(os.environ, {"GITHUB_EVENT_NAME": "schedule"}), patch.object(app, "datetime") as clock, patch.object(app.time, "sleep") as sleep:
            clock.now.return_value = datetime(2026, 10, 18, 15, 7, tzinfo=timezone.utc)
            app.wait_for_scheduled_window()
            sleep.assert_called_once_with(10380.0)

    def test_manual_run_does_not_wait(self):
        with patch.dict(os.environ, {"GITHUB_EVENT_NAME": "workflow_dispatch"}), patch.object(app.time, "sleep") as sleep:
            app.wait_for_scheduled_window()
            sleep.assert_not_called()

    def test_weekly_window_preserved(self):
        start, end, _, _ = app.get_collage_window(datetime(2026, 10, 11, 23, tzinfo=timezone.utc))
        self.assertEqual(start, datetime(2026, 10, 4, 18, tzinfo=timezone.utc))
        self.assertEqual(end, datetime(2026, 10, 11, 18, tzinfo=timezone.utc))
        self.assertNotEqual(app.delivery_ref(end), app.delivery_ref(start))


if __name__ == "__main__":
    unittest.main()
