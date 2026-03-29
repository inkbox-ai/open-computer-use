from os_computer_use.config import vision_model, action_model, grounding_model
from os_computer_use.llm_provider import Message
from os_computer_use.logging import logger
from os_computer_use.grounding import draw_big_dot

import os
import tempfile
from PIL import Image
import json
import re

TYPING_DELAY_MS = 12
TYPING_GROUP_SIZE = 50

tools = {
    "stop": {
        "description": "Indicate that the task has been completed.",
        "params": {},
    }
}


class SandboxAgent:

    def __init__(self, sandbox, output_dir=".", save_logs=True, inkbox_context=None):
        super().__init__()
        self.messages = []  # Agent memory
        self.sandbox = sandbox  # E2B sandbox
        self.inkbox_context = inkbox_context
        self.latest_screenshot = None  # Most recent PNG of the screen
        self.image_counter = 0  # Current screenshot number
        self.tmp_dir = tempfile.mkdtemp()  # Folder to store screenshots

        # Set the log file location
        if save_logs:
            logger.log_file = f"{output_dir}/log.html"

        # Register inkbox tools as native actions if available
        if inkbox_context:
            self._register_inkbox_tools()

        print("The agent will use the following actions:")
        for action, details in tools.items():
            param_str = ", ".join(details.get("params").keys())
            print(f"- {action}({param_str})")

    def call_function(self, name, arguments):

        func_impl = getattr(self, name.lower()) if name.lower() in tools else None
        if func_impl:
            try:
                result = func_impl(**arguments) if arguments else func_impl()
                return result
            except Exception as e:
                return f"Error executing function: {str(e)}"
        else:
            return "Function not implemented."

    def tool(description, params):
        def decorator(func):
            tools[func.__name__] = {"description": description, "params": params}
            return func

        return decorator

    def save_image(self, image, prefix="image"):
        self.image_counter += 1
        filename = f"{prefix}_{self.image_counter}.png"
        filepath = os.path.join(self.tmp_dir, filename)
        if isinstance(image, Image.Image):
            image.save(filepath)
        else:
            with open(filepath, "wb") as f:
                f.write(image)
        return filepath

    def screenshot(self):
        file = self.sandbox.screenshot()
        filename = self.save_image(file, "screenshot")
        logger.log(f"screenshot {filename}", "gray")
        self.latest_screenshot = filename
        with open(filename, "rb") as image_file:
            return image_file.read()

    @tool(
        description="Run a shell command and return the result.",
        params={"command": "Shell command to run synchronously"},
    )
    def run_command(self, command):
        result = self.sandbox.commands.run(command, timeout=30)
        stdout, stderr = result.stdout, result.stderr
        if stdout and stderr:
            return stdout + "\n" + stderr
        elif stdout or stderr:
            return stdout + stderr
        else:
            return "The command finished running."

    @tool(
        description="Run a shell command in the background.",
        params={"command": "Shell command to run asynchronously"},
    )
    def run_background_command(self, command):
        self.sandbox.commands.run(command, background=True)
        return "The command has been started."

    @tool(
        description="Send a key or combination of keys to the system.",
        params={"name": "Key or combination (e.g. 'Return', 'Ctl-C')"},
    )
    def send_key(self, name):
        self.sandbox.press(name)
        return "The key has been pressed."

    @tool(
        description="Type a specified text into the system.",
        params={"text": "Text to type"},
    )
    def type_text(self, text):
        self.sandbox.write(text, chunk_size=TYPING_GROUP_SIZE, delay_in_ms=TYPING_DELAY_MS)
        return "The text has been typed."

    def click_element(self, query, click_command, action_name="click"):
        """Base method for all click operations"""
        self.screenshot()
        position = grounding_model.call(query, self.latest_screenshot)
        dot_image = draw_big_dot(Image.open(self.latest_screenshot), position)
        filepath = self.save_image(dot_image, "location")
        logger.log(f"{action_name} {filepath})", "gray")

        x, y = position
        self.sandbox.move_mouse(x, y)
        click_command()
        return f"The mouse has {action_name}ed."

    @tool(
        description="Click on a specified UI element.",
        params={"query": "Item or UI element on the screen to click"},
    )
    def click(self, query):
        return self.click_element(query, self.sandbox.left_click)

    @tool(
        description="Double click on a specified UI element.",
        params={"query": "Item or UI element on the screen to double click"},
    )
    def double_click(self, query):
        return self.click_element(query, self.sandbox.double_click, "double click")

    @tool(
        description="Right click on a specified UI element.",
        params={"query": "Item or UI element on the screen to right click"},
    )
    def right_click(self, query):
        return self.click_element(query, self.sandbox.right_click, "right click")

    def append_screenshot(self):
        return vision_model.call(
            [
                *self.messages,
                Message(
                    [
                        self.screenshot(),
                        "This image shows the current display of the computer. Please respond in the following format:\n"
                        "The objective is: [put the objective here]\n"
                        "On the screen, I see: [an extensive list of everything that might be relevant to the objective including windows, icons, menus, apps, and UI elements]\n"
                        "This means the objective is: [complete|not complete]\n\n"
                        "(Only continue if the objective is not complete.)\n"
                        "The next step is to [click|type|run the shell command|send_email|get_email_address|list_emails|read_email] [put the next single step here] in order to [put what you expect to happen here].",
                    ],
                    role="user",
                ),
            ]
        )

    def _build_system_prompt(self):
        prompt = "You are an AI assistant with computer use abilities."
        if self.inkbox_context:
            prompt += f"""

You have the Inkbox SDK and native Inkbox tools available.
Prefer native email tools such as send_email instead of trying to use a GUI mail client or composing shell scripts manually.

Inkbox details:
- Agent handle: {self.inkbox_context['agent_handle']}
- Your email address: {self.inkbox_context['mailbox_email']}
- The INKBOX_API_KEY environment variable is already set.
- Recipient addresses must be complete valid emails. Example: alex@vectorly.app is valid; alex@vectorly is not.

Use run_command for Inkbox only as a fallback.
"""
        return prompt

    def _register_inkbox_tools(self):
        """Register inkbox email tools as native agent actions."""
        ctx = self.inkbox_context
        handle = ctx["agent_handle"]
        email = ctx["mailbox_email"]
        api_key_env = ctx["inkbox_api_key_env"]

        def _run_inkbox_script(script):
            """Write a Python script to the sandbox and execute it with inkbox env."""
            self.sandbox.files.write("/tmp/_inkbox_action.py", script)
            result = self.sandbox.commands.run(
                f"bash -c 'source ~/.bashrc && python3.11 /tmp/_inkbox_action.py'",
                timeout=30,
            )
            stdout, stderr = result.stdout or "", result.stderr or ""
            if result.exit_code != 0:
                raise Exception(stderr or stdout or "Script failed")
            return stdout.strip()

        def _inkbox_preamble():
            return (
                "import os\n"
                "from inkbox import Inkbox\n"
                f'inkbox = Inkbox(api_key=os.environ["{api_key_env}"])\n'
                f'inkbox.__enter__()\n'
                f'identity = inkbox.get_identity("{handle}")\n'
            )

        # -- get_email_address --
        def get_email_address(self_agent):
            return f"Your email address is: {email}"

        tools["get_email_address"] = {
            "description": "Get the agent's email address. Use this when you need to provide an email address.",
            "params": {},
        }
        self.get_email_address = lambda: get_email_address(self)

        # -- send_email --
        def send_email(self_agent, to, subject, body):
            recipients = [addr.strip() for addr in to.split(",")]
            invalid = [
                addr
                for addr in recipients
                if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", addr)
            ]
            if invalid:
                return (
                    "Invalid recipient email address(es): "
                    + ", ".join(invalid)
                    + ". Use complete addresses such as name@example.com."
                )
            script = _inkbox_preamble() + (
                f'identity.send_email(\n'
                f'    to={json.dumps(recipients)},\n'
                f'    subject={json.dumps(subject)},\n'
                f'    body_text={json.dumps(body)},\n'
                f')\n'
                f'print("Email sent successfully to: " + {json.dumps(to)})\n'
            )
            return _run_inkbox_script(script)

        tools["send_email"] = {
            "description": "Send an email from the agent's mailbox. For multiple recipients, separate email addresses with commas in the 'to' field.",
            "params": {
                "to": "Recipient email address(es), comma-separated for multiple",
                "subject": "Email subject line",
                "body": "Email body text",
            },
        }
        self.send_email = lambda to, subject, body: send_email(self, to, subject, body)

        # -- list_emails --
        def list_emails(self_agent):
            script = _inkbox_preamble() + (
                "import itertools, json\n"
                "emails = list(itertools.islice(identity.iter_emails(), 10))\n"
                "if not emails:\n"
                "    print('No emails found.')\n"
                "else:\n"
                "    for e in emails:\n"
                "        print(f'ID: {e.id} | From: {e.from_address} | Subject: {e.subject}')\n"
            )
            return _run_inkbox_script(script)

        tools["list_emails"] = {
            "description": "List recent emails in the agent's inbox.",
            "params": {},
        }
        self.list_emails = lambda: list_emails(self)

        # -- read_email --
        def read_email(self_agent, message_id):
            script = _inkbox_preamble() + (
                f'msg = identity.get_message("{message_id}")\n'
                'body = msg.body_text or ""\n'
                'if not body and msg.body_html:\n'
                '    body = msg.body_html\n'
                'print(f"From: {msg.from_address}")\n'
                'print(f"Subject: {msg.subject}")\n'
                'print(f"Body: {body}")\n'
            )
            return _run_inkbox_script(script)

        tools["read_email"] = {
            "description": "Read the full body of a specific email by its message ID.",
            "params": {"message_id": "The ID of the email to read"},
        }
        self.read_email = lambda message_id: read_email(self, message_id)

    def run(self, instruction):

        self.messages.append(Message(f"OBJECTIVE: {instruction}"))
        logger.log(f"USER: {instruction}", print=False)

        should_continue = True
        while should_continue:
            # Stop the sandbox from timing out
            self.sandbox.set_timeout(60)

            content, tool_calls = action_model.call(
                [
                    Message(
                        self._build_system_prompt(),
                        role="system",
                    ),
                    *self.messages,
                    Message(
                        logger.log(f"THOUGHT: {self.append_screenshot()}", "green")
                    ),
                    Message(
                        "I will now use tool calls to take these actions, or use the stop command if the objective is complete.",
                    ),
                ],
                tools,
            )

            if content:
                self.messages.append(Message(logger.log(f"THOUGHT: {content}", "blue")))

            should_continue = False
            for tool_call in tool_calls:
                name, parameters = tool_call.get("name"), tool_call.get("parameters")
                should_continue = name != "stop"
                if not should_continue:
                    break
                # Print the tool-call in an easily readable format
                logger.log(f"ACTION: {name} {str(parameters)}", "red")
                # Write the tool-call to the message history using the same format used by the model
                self.messages.append(Message(json.dumps(tool_call)))
                result = self.call_function(name, parameters)

                self.messages.append(
                    Message(logger.log(f"OBSERVATION: {result}", "yellow"))
                )
