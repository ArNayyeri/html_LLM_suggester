import json
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import recorder_server as server


def response(content, reason='stop'):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=reason)])


class OpenRouterFailoverTests(unittest.TestCase):
    def test_empty_and_invalid_responses_fall_back_for_both_endpoints(self):
        valid = json.dumps({'id': 'q', 'name': 'q', 'type': 'text', 'range': 'text',
                            'examples': ['one'], 'bad_examples': ['']})
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(server, 'RUN_SAVE_DIR', directory), \
             patch.object(server, 'selected_mode', 'openrouter'), \
             patch.object(server.client.chat.completions, 'create', side_effect=[
                 response('', 'length'), response('not JSON'), response(valid),
                 response('', 'length'), response(valid)]) as create:
            client = server.app.test_client()
            first = client.post('/suggest_inputs', json={'html': '<input id="q" name="q">'})
            second = client.post('/update_input_suggestion', json={'field': 'q'})
            self.assertEqual(first.status_code, 200)
            self.assertEqual(first.get_json()[0]['examples'], ['one'])
            self.assertEqual(second.status_code, 200)
            self.assertEqual(second.get_json()['new_examples'], ['one'])
            self.assertEqual(create.call_count, 5)

    def test_exhausted_models_return_error_instead_of_fake_success(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(server, 'RUN_SAVE_DIR', directory), \
             patch.object(server, 'selected_mode', 'openrouter'), \
             patch.object(server.client.chat.completions, 'create', return_value=response('')):
            client = server.app.test_client()
            for path, payload in [('/suggest_inputs', {'html': '<input id="q">'}),
                                  ('/update_input_suggestion', {'field': 'q'})]:
                result = client.post(path, json=payload)
                self.assertEqual(result.status_code, 500)
                self.assertIn('All OpenRouter free models failed', result.get_json()['error'])

    def test_incomplete_fields_retry(self):
        item = {'id': 'one', 'range': 'text', 'examples': ['ok'], 'bad_examples': ['']}
        second = dict(item, id='two')
        with patch.object(server, 'selected_mode', 'openrouter'), \
             patch.object(server.client.chat.completions, 'create', side_effect=[
                 response(json.dumps([item])), response(json.dumps([item, second]))]) as create:
            fields = [{'id': key, 'name': key, 'type': 'text'} for key in ('one', 'two')]
            result = server.generate_field_suggestions(fields)
            self.assertEqual({item['id'] for item in result}, {'one', 'two'})
            self.assertEqual(create.call_count, 2)

    def test_closing_assistant_requests_shutdown(self):
        improver = server.KatalonTestImprover.__new__(server.KatalonTestImprover)
        improver.root = Mock()
        with patch.object(server, 'request_server_shutdown') as shutdown:
            improver.on_closing()
            improver.root.destroy.assert_called_once()
            shutdown.assert_called_once()


if __name__ == '__main__':
    unittest.main()
