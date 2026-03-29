# Define the models to use in the agent

from os_computer_use import providers

# Both HuggingFace Spaces (OSAtlas and ShowUI) are currently down.
# Set grounding_model = None to skip grounding and use coordinate-free mode.
# grounding_model = providers.OSAtlasProvider()
# grounding_model = providers.ShowUIProvider()
grounding_model = providers.OpenAIProvider("gpt-5.2")

# vision_model = providers.FireworksProvider("llama-3.2")
# vision_model = providers.OpenAIProvider("gpt-4o")
# vision_model = providers.AnthropicProvider("claude-3.5-sonnet")
# vision_model = providers.MoonshotProvider("moonshot-v1-vision")
# vision_model = providers.MistralProvider("pixtral")
# vision_model = providers.GroqProvider("llama-3.2")
# vision_model = providers.OpenRouterProvider("qwen-2.5-vl")
vision_model = providers.OpenAIProvider("gpt-5.2")

# action_model = providers.FireworksProvider("llama-3.3")
# action_model = providers.OpenAIProvider("gpt-4o")
# action_model = providers.AnthropicProvider("claude-3.5-sonnet")
# vision_model = providers.MoonshotProvider("moonshot-v1-vision")
# action_model = providers.MistralProvider("mistral")
action_model = providers.OpenAIProvider("gpt-5.2")
