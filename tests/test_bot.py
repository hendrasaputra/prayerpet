"""Telegram bot against a fake Telegram server: allow-list, commands, reminders, Gemini fallback."""
import io
import json
import os
import time
import unittest
import urllib.error
from datetime import datetime, timedelta

from tests.helpers import IsolatedHome


def msg(uid, text, chat_type="private", n=0):
    return dict(update_id=n, message={"from": {"id": uid, "username": f"u{uid}"},
                                      "chat": {"id": uid, "type": chat_type}, "text": text})


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


class TestBot(IsolatedHome):
    def setUp(self):
        super().setUp()
        secrets = os.path.join(self.home, ".prayerpet-telegram.toml")
        with open(secrets, "w") as f:
            f.write('token = "123:TEST"\nallowed_ids = [42]\nremind_before_minutes = 10\n')
        os.chmod(secrets, 0o644)
        with open(os.path.join(self.home, ".prayerpet-weather.json"), "w") as f:
            json.dump(dict(lat=-6.2088, lon=106.8456, temp=31.2, code=63, humidity=75, feels=36, hi=33, lo=25,
                           rain_max=80, hours=[], aqi=118, pm25=44, weather_at=time.time()), f)
        from prayerpet import bot, config, inbox
        self.bot, self.inbox = bot, inbox
        self.cfg = config.load("~/prayerpet.toml")
        self.cfg["prayer"]["language"] = "en"

    def run_bot(self, updates, at=None):
        """Run the bot loop once against a fake Telegram; returns (texts sent, photos sent)."""
        sent, photos, state = [], [], {"n": 0}

        class FakeTG:
            def __init__(self, token):
                pass

            def call(self, method, http_timeout=35, **p):
                if method == "getMe":
                    return {"username": "testbot"}
                if method == "setMyCommands":
                    return True
                if method == "getUpdates":
                    if state["n"] == 0:
                        state["n"] = 1
                        return updates
                    raise KeyboardInterrupt  # ends the loop

            def send(self, chat_id, text):
                sent.append((chat_id, text))

            def send_photo(self, chat_id, png, caption=""):
                photos.append((chat_id, len(png)))

        self.bot.Telegram = FakeTG
        orig_now = self.bot.Context.now
        if at:
            self.bot.Context.now = lambda self_: at
        try:
            self.bot.main(self.cfg)
        finally:
            self.bot.Context.now = orig_now
        return sent, photos

    def test_secrets_file_permissions_tightened(self):
        self.bot.load_secrets()
        self.assertEqual(os.stat(self.bot.SECRETS).st_mode & 0o777, 0o600)

    def test_ignores_strangers_and_group_chats(self):
        sent, _ = self.run_bot([msg(99, "/status", n=1), msg(42, "/status", "group", n=2)])
        self.assertEqual(sent, [])

    def test_commands_answer_the_owner(self):
        tz = self.bot.ZoneInfo("Asia/Jakarta")
        sent, _ = self.run_bot([msg(42, "/times", n=1), msg(42, "/next", n=2), msg(42, "/weather", n=3),
                                msg(42, "/say Dinner at 7", n=4), msg(42, "/bogus", n=5)],
                               at=datetime(2026, 10, 31, 14, 20, tzinfo=tz))
        texts = [t for _, t in sent]
        self.assertIn("Asr", texts[0])
        self.assertIn("in ", texts[1])
        self.assertIn("AQI 118", texts[2])
        self.assertIn("Dinner at 7", texts[3])
        self.assertIn("/times", texts[4])  # unknown command -> help text
        self.assertEqual([d["kind"] for d in self.inbox.drain()], ["say"])

    def test_feed_refused_while_pet_asleep(self):
        ctx = self.bot.Context(self.cfg)
        ctx.now = lambda: datetime(2026, 10, 31, 22, 0, tzinfo=ctx.tz)
        self.assertIn("asleep", self.bot.cmd_feed(ctx, ""))
        self.assertEqual(self.inbox.drain(), [])
        ctx.now = lambda: datetime(2026, 10, 31, 10, 0, tzinfo=ctx.tz)
        self.bot.cmd_feed(ctx, "")
        self.assertEqual([d["kind"] for d in self.inbox.drain()], ["feed"])

    def test_reminders_fire_once_each(self):
        ctx = self.bot.Context(self.cfg)
        rem = self.bot.Reminders(ctx, self.bot.load_secrets())
        t0 = datetime(2026, 10, 31, 14, 40, tzinfo=ctx.tz)
        out = []
        for m in range(23):
            ctx.now = (lambda m=m: t0 + timedelta(minutes=m))
            out += rem.due()
        self.assertEqual(len(out), 2)  # 10 min before Asr (14:54) and at 14:54

    def test_gemini_retired_model_falls_back(self):
        ctx = self.bot.Context(self.cfg)
        sec = self.bot.load_secrets()
        sec.update(gemini_api_key="FAKE", gemini_model="gemini-2.5-flash-lite", ask_daily_limit=5)
        tried = []

        def fake_urlopen(req, timeout=0):
            model = req.full_url.split("/models/")[1].split(":")[0]
            tried.append(model)
            if model == "gemini-2.5-flash-lite":  # wording copied from Google's real 404 (2026-11)
                body = json.dumps({"error": {"code": 404, "message":
                    "This model models/gemini-2.5-flash-lite is no longer available to new users. "
                    "Please update your code to use models/gemini-3.5-flash-lite for the latest features."}}).encode()
                raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, io.BytesIO(body))
            return FakeResponse(json.dumps(
                {"candidates": [{"content": {"parts": [{"text": "Take an umbrella."}]}}]}).encode())

        orig = self.bot.urllib.request.urlopen
        self.bot.urllib.request.urlopen = fake_urlopen
        try:
            answer = self.bot.ask_gemini(ctx, sec, "umbrella?")
        finally:
            self.bot.urllib.request.urlopen = orig
        self.assertTrue(answer.startswith("Take an umbrella."))
        self.assertIn("gemini-3.5-flash-lite", answer)
        self.assertEqual(tried, ["gemini-2.5-flash-lite", "gemini-3.5-flash-lite"])

    def test_ask_daily_limit(self):
        ctx = self.bot.Context(self.cfg)
        sec = self.bot.load_secrets()
        sec.update(gemini_api_key="FAKE", ask_daily_limit=0)
        self.assertIn("limit", self.bot.ask_gemini(ctx, sec, "hi"))


if __name__ == "__main__":
    unittest.main()
