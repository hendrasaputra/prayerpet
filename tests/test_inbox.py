"""The drop-box folder that lets the bot, the AI assistant and the shell talk to the running app."""
import json
import os
import unittest

from tests.helpers import IsolatedHome


class TestInbox(IsolatedHome):
    def test_post_and_drain_in_order(self):
        from prayerpet import inbox
        inbox.post("say", text="hello\nworld\t!", minutes=5)
        inbox.post("feed")
        items = inbox.drain()
        self.assertEqual([i["kind"] for i in items], ["say", "feed"])
        self.assertEqual(items[0]["text"], "hello world !")  # newlines and tabs collapsed
        self.assertEqual(inbox.drain(), [])

    def test_text_is_capped(self):
        from prayerpet import inbox
        inbox.post("say", text="x" * 1000)
        self.assertEqual(len(inbox.drain()[0]["text"]), inbox.MAX_TEXT)

    def test_unknown_kinds_are_dropped(self):
        from prayerpet import inbox
        os.makedirs(inbox.INBOX, exist_ok=True)
        with open(os.path.join(inbox.INBOX, "1-other.json"), "w") as f:
            json.dump({"kind": "shell", "cmd": "anything"}, f)
        self.assertEqual(inbox.drain(), [])


if __name__ == "__main__":
    unittest.main()
