import unittest

from tradingagents.llm_clients.factory import create_llm_client
from tradingagents.llm_clients.anthropic_client import AnthropicClient
from tradingagents.llm_clients.openai_client import OpenAIClient
from tradingagents.llm_clients.provider_keys import default_backend_url, env_key_for_provider


class MinimaxProviderTest(unittest.TestCase):
    def test_minimax_uses_anthropic_compatible_client(self):
        client = create_llm_client(provider="minimax", model="MiniMax-M2.7-highspeed")
        self.assertIsInstance(client, AnthropicClient)
        self.assertEqual(client.provider, "minimax")

    def test_minimax_env_and_backend_defaults(self):
        self.assertEqual(env_key_for_provider("minimax"), "MINIMAX_API_KEY")
        self.assertEqual(default_backend_url("minimax"), "https://api.minimaxi.com/anthropic")

    def test_minimax_is_not_available_through_openai_client(self):
        with self.assertRaisesRegex(ValueError, "MiniMax"):
            OpenAIClient(model="MiniMax-M2.7-highspeed", provider="minimax").get_llm()


if __name__ == "__main__":
    unittest.main()
