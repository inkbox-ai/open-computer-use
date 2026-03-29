from os_computer_use.sandbox_agent import SandboxAgent


# This is a mock sandbox that returns a static screenshot and terminal output
class MockSandbox:
    def __init__(self):
        self.timeout = 60
        self.commands = self
        self.files = self
        self.written_files = {}

    def screenshot(self):
        with open("./tests/test_screenshot.png", "rb") as f:
            return f.read()

    def run(self, command, timeout=None, background=False):
        class MockResult:
            def __init__(self):
                self.stdout = f"Mock stdout for command: {command}"
                self.stderr = ""
                self.exit_code = 0

        return MockResult()

    def write(self, path, content):
        self.written_files[path] = content

    def set_timeout(self, timeout):
        self.timeout = timeout


def test_send_email_rejects_invalid_addresses():
    sandbox = MockSandbox()
    agent = SandboxAgent(
        sandbox,
        save_logs=False,
        inkbox_context={
            "agent_handle": "ocu-test1234",
            "mailbox_email": "tester@example.com",
            "inkbox_api_key_env": "INKBOX_API_KEY",
        },
    )

    result = agent.send_email("ray@vectorly.app, alex@vectorly", "Intro", "Hi")

    assert "Invalid recipient email address(es): alex@vectorly" in result


def test_build_system_prompt_mentions_native_inkbox_tools():
    sandbox = MockSandbox()
    agent = SandboxAgent(
        sandbox,
        save_logs=False,
        inkbox_context={
            "agent_handle": "ocu-test1234",
            "mailbox_email": "tester@example.com",
            "inkbox_api_key_env": "INKBOX_API_KEY",
        },
    )

    prompt = agent._build_system_prompt()

    assert "Prefer native email tools such as send_email" in prompt


if __name__ == "__main__":
    # Create an instance of SandboxAgent with the mock sandbox
    agent = SandboxAgent(MockSandbox(), save_logs=False)

    # Test the agent with a sample instruction
    # This will verify that the model providers are working correctly.
    test_instruction = "Open the Firefox browser"
    print("\nRunning test with instruction:", test_instruction)
    agent.run(test_instruction)
