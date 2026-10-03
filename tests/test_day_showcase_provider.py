import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from engine import chitatel as reader


class Response:
    def __init__(self, payload, status=200):
        self.payload, self.status = payload, status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def json(self, **kwargs):
        return self.payload


class Session(Response):
    def post(self, url, **kwargs):
        self.request = (url, kwargs)
        return self


class ShowcaseProviderTests(unittest.TestCase):
    def response(self, text="A complete forecast", finish="stop"):
        return {"choices": [{"message": {"content": text}, "finish_reason": finish}],
                "usage": {"prompt_tokens": 12790, "completion_tokens": 1403,
                          "completion_tokens_details": {"reasoning_tokens": 1173}}}

    def call(self, session):
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-secret",
                                     "DAY_SHOWCASE_PROVIDER": "groq"}), \
                patch("aiohttp.ClientSession", return_value=session):
            return reader._спросить_витрину("system", [{"role": "user", "content": "machine"}])

    def test_groq_request_and_cost_include_reasoning_once(self):
        session = Session(self.response())
        with patch.object(reader, "_ПОТРАЧЕНО", {"$": 0.0, "вызовов": 0}):
            self.assertEqual(self.call(session), "A complete forecast")
            body = session.request[1]["json"]
            self.assertEqual(body["model"], "openai/gpt-oss-120b")
            self.assertEqual(body["messages"], [{"role": "system", "content": "system"},
                                               {"role": "user", "content": "machine"}])
            self.assertAlmostEqual(reader._ПОТРАЧЕНО["$"], 0.0027603)

    def test_empty_response_is_not_delivered(self):
        with self.assertRaisesRegex(RuntimeError, "пустой"):
            self.call(Session(self.response(text="")))

    def test_truncated_response_is_not_delivered(self):
        with self.assertRaisesRegex(RuntimeError, "оборван"):
            self.call(Session(self.response(finish="length")))

    def test_error_does_not_fall_back_or_expose_key(self):
        with patch.object(reader, "_спросить") as fallback:
            with self.assertRaises(RuntimeError) as error:
                self.call(Session({"error": {"message": "bad test-secret"}}, status=401))
            self.assertNotIn("test-secret", str(error.exception))
            fallback.assert_not_called()

    def test_explicit_gemini_rollback(self):
        with patch.dict(os.environ, {"DAY_SHOWCASE_PROVIDER": "gemini"}), \
                patch.object(reader, "_спросить", return_value="old forecast") as old:
            self.assertEqual(reader._спросить_витрину("s", [], максимум=8000), "old forecast")
            old.assert_called_once_with("s", [], максимум=8000, бесплатно=True)

    def test_paid_reader_still_uses_gemini(self):
        with patch.object(reader, "ЧИТАТЕЛЬ", "gemini"), \
                patch.object(reader, "_спросить_gemini", return_value="paid") as gemini:
            self.assertEqual(reader._спросить_раз("s", [], бесплатно=False), "paid")
            self.assertFalse(gemini.call_args.kwargs["бесплатно"])

    def test_daily_modes_route_only_showcase_to_groq(self):
        from engine import karta_dnya as day
        moment = datetime(2026, 10, 3, 4, tzinfo=timezone.utc)
        shelf = {"местное": moment, "полка": "machine facts", "окна": {},
                 "точки": {"Венера": {"знак": "Скорпион"}}}
        for mode in ("витрина", "полный"):
            with self.subTest(mode=mode), \
                    patch.object(day, "полочка_дня", return_value=shelf.copy()), \
                    patch.object(day, "зачин_машины", return_value="machine intro"), \
                    patch.object(day, "часы_текстом", return_value="machine hours"), \
                    patch.object(day, "градусы_машиной", side_effect=lambda t, d: (t, 0)), \
                    patch.object(reader, "_спросить_витрину", return_value="## ИТОГ\n\n" + "Смысл дня. " * 70) as groq, \
                    patch.object(reader, "_спросить", return_value="## ИТОГ\n\n" + "Смысл дня. " * 1500) as paid:
                day.прочитать_день(moment, 56.85, 53.233333, 4, режим=mode)
                if mode == "витрина":
                    groq.assert_called_once()
                    paid.assert_not_called()
                    self.assertIn('"Венера": "Скорпион"', groq.call_args.args[1][0]["content"])
                else:
                    paid.assert_called_once()
                    groq.assert_not_called()


if __name__ == "__main__":
    unittest.main()
