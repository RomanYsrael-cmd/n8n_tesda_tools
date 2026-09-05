import unittest
from unittest.mock import patch

import httpx

from app.providers import OpenAICompatibleProvider, ProviderError


class StreamDiagnosticsTests(unittest.IsolatedAsyncioTestCase):
    async def run_stream(self, body):
        transport = httpx.MockTransport(lambda request: httpx.Response(
            200, text=body, headers={'content-type': 'text/event-stream',
                                     'x-qwen-request-id': 'request-123',
                                     'authorization': 'never-log-this'}))
        real_client = httpx.AsyncClient
        with patch('app.providers.httpx.AsyncClient', side_effect=lambda **kw: real_client(transport=transport, **kw)):
            return await OpenAICompatibleProvider('https://example.test/v1', 'secret-key', 'test').complete_text('test', max_attempts=1)

    async def test_reasoning_only_and_keepalives_are_identified(self):
        with self.assertRaises(ProviderError) as caught:
            await self.run_stream(': keepalive\n\ndata: {"choices":[{"delta":{"reasoning_content":"private"},"finish_reason":"length"}]}\n\ndata: [DONE]\n\n')
        info = caught.exception.stream_diagnostics[0]
        self.assertEqual(info['reasoning_characters'], 7)
        self.assertEqual(info['keepalive_comments'], 1)
        self.assertEqual(info['content_characters'], 0)
        self.assertEqual(info['finish_reasons'], ['length'])
        self.assertTrue(info['done_received'])
        for sensitive in ('private', 'secret-key', 'never-log-this'):
            self.assertNotIn(sensitive, str(caught.exception))

    async def test_stream_error_and_malformed_event_counted(self):
        with self.assertRaises(ProviderError) as caught:
            await self.run_stream('data: {bad\n\ndata: {"error":{"message":"private error"}}\n\n')
        info = caught.exception.stream_diagnostics[0]
        self.assertEqual(info['malformed_events'], 1)
        self.assertEqual(info['error_events'], 1)
        self.assertNotIn('private error', str(caught.exception))

    async def test_success_content_unchanged(self):
        self.assertEqual(await self.run_stream(': ping\n\ndata: {"choices":[{"delta":{"content":"Hello"}}]}\n\ndata: [DONE]\n\n'), 'Hello')

    async def test_progress_callback_reports_usage_and_output_stats(self):
        progress = []
        body = 'data: {"choices":[{"delta":{"content":"Hello"}}],"usage":{"prompt_tokens":10,"completion_tokens":2,"total_tokens":12}}\n\ndata: [DONE]\n\n'
        transport = httpx.MockTransport(lambda request: httpx.Response(
            200, text=body, headers={'content-type': 'text/event-stream'}))
        real_client = httpx.AsyncClient
        with patch('app.providers.httpx.AsyncClient', side_effect=lambda **kw: real_client(transport=transport, **kw)):
            result = await OpenAICompatibleProvider('https://example.test/v1', '', 'test').complete_text(
                'test', max_attempts=1, on_progress=progress.append)
        self.assertEqual(result, 'Hello')
        self.assertTrue(progress)
        self.assertEqual(progress[-1]['usage']['completion_tokens'], 2)
        self.assertEqual(progress[-1]['content_characters'], 5)


if __name__ == '__main__':
    unittest.main()
