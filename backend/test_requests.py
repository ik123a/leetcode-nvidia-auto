"""Offline Flask boundary tests. Provider functions are replaced before import."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch


class RequestValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        solvers = types.ModuleType('solvers')
        solvers.MODELS = ['offline-model']
        solvers.call_model = AsyncMock()
        solvers.call_model_with_history = AsyncMock()
        judge = types.ModuleType('judge')
        judge.judge_solutions = AsyncMock()
        spec = importlib.util.spec_from_file_location('offline_backend', Path(__file__).with_name('main.py'))
        cls.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'solvers': solvers, 'judge': judge}), patch('dotenv.load_dotenv'):
            spec.loader.exec_module(cls.module)
        cls.client = cls.module.app.test_client()

    def test_non_object_json_is_rejected_before_provider_dispatch(self):
        with patch.object(self.module, '_solve', new_callable=AsyncMock) as solve, \
             patch.object(self.module, '_solve_evolve', new_callable=AsyncMock) as evolve:
            for endpoint in ['/solve', '/solve_evolve']:
                for body in ['null', '[]', '"text"', '1', 'true', '{broken']:
                    with self.subTest(endpoint=endpoint, body=body):
                        response = self.client.post(endpoint, data=body, content_type='application/json')
                        self.assertEqual(response.status_code, 400)
                        self.assertFalse(response.get_json()['success'])
            solve.assert_not_awaited()
            evolve.assert_not_awaited()

    def test_valid_request_preserves_success_response(self):
        with patch.object(self.module, '_solve', new_callable=AsyncMock,
                          return_value=('synthetic code', [])) as solve:
            response = self.client.post('/solve', json={'title': 'Offline', 'description': 'Fixture'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()['code'], 'synthetic code')
            solve.assert_awaited_once()


if __name__ == '__main__':
    unittest.main()
