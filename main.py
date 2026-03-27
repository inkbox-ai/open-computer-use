from os_computer_use.streaming import Sandbox, DisplayClient
from os_computer_use.browser import Browser
from os_computer_use.sandbox_agent import SandboxAgent
from os_computer_use.logging import Logger
import asyncio
import argparse

import os
from dotenv import load_dotenv

logger = Logger()

# Load environment variables from .env file
load_dotenv()

# Configure E2B
os.environ["E2B_API_KEY"] = os.getenv("E2B_API_KEY")


async def start(user_input=None, output_dir=None):
    sandbox = None
    client = None
    
    try:
        sandbox = Sandbox()

        # Pre-install inkbox SDK and configure API key in sandbox
        inkbox_api_key = os.getenv("INKBOX_API_KEY")
        if inkbox_api_key:
            print("Installing Python 3.11 and inkbox SDK in sandbox...")
            sandbox.commands.run("sudo apt-get update -qq && sudo apt-get install -y -qq python3.11 python3.11-venv python3.11-dev > /dev/null 2>&1", timeout=120)
            sandbox.commands.run("curl -sS https://bootstrap.pypa.io/get-pip.py | python3.11", timeout=60)
            sandbox.commands.run("python3.11 -m pip install inkbox", timeout=120)
            sandbox.commands.run(f"echo 'export INKBOX_API_KEY={inkbox_api_key}' >> ~/.bashrc")
            print("Inkbox SDK installed (use python3.11 to run scripts).")

            # Create inkbox identity and mailbox inside the sandbox
            print("Setting up inkbox identity...")
            setup_script = "\n".join([
                "import os",
                "from inkbox import Inkbox",
                f'os.environ["INKBOX_API_KEY"] = "{inkbox_api_key}"',
                'with Inkbox(api_key=os.environ["INKBOX_API_KEY"]) as inkbox:',
                '    try:',
                '        identity = inkbox.get_identity("computer-use-bot")',
                '    except Exception:',
                '        identity = inkbox.create_identity("computer-use-bot")',
                '    if not identity.mailbox:',
                '        identity.create_mailbox(display_name="Computer Use Bot")',
                '        identity.refresh()',
                '    print(f"Identity ready: {identity.agent_handle}")',
                '    if identity.mailbox:',
                '        print(f"Mailbox: {identity.mailbox.email_address}")',
            ])
            sandbox.files.write("/tmp/setup_inkbox.py", setup_script)
            result = sandbox.commands.run("python3.11 /tmp/setup_inkbox.py", timeout=30)
            print(result.stdout.strip() if result.stdout else "Inkbox identity ready.")

        # The display server won't work on desktop-dev-v2 since ffmpeg is not installed
        #client = DisplayClient(output_dir)
        #print("Starting the display server...")
        #stream_url = sandbox.start_stream()
        #print("(The display client will start in five seconds.)")
        # If the display client is opened before the stream is ready, it will close immediately
        #await client.start(stream_url, user_input or "Sandbox", delay=5)

        agent = SandboxAgent(sandbox, output_dir)

        print("Starting the VNC server...")
        sandbox.stream.start()
        vnc_url = sandbox.stream.get_url()

        print("Starting the VNC client...")
        browser = Browser()
        browser.open(vnc_url)

        while True:
            # Ask for user input, and exit if the user presses ctl-c
            if user_input is None:
                try:
                    user_input = input("USER: ")
                except KeyboardInterrupt:
                    break
            # Run the agent, and go back to the prompt if the user presses ctl-c
            else:
                try:
                    agent.run(user_input)
                    user_input = None
                except KeyboardInterrupt:
                    user_input = None
                except Exception as e:
                    logger.print_colored(f"An error occurred: {e}", "red")
                    user_input = None

    finally:
        #if client:
        #    print("Stopping the display client...")
        #    try:
        #        await client.stop()
        #    except Exception as e:
        #        print(f"Error stopping display client: {str(e)}")

        if sandbox:
            print("Stopping the sandbox...")
            try:
                sandbox.kill()
            except Exception as e:
                print(f"Error stopping sandbox: {str(e)}")

        #if client:
        #    print("Saving the stream as mp4...")
        #    try:
        #        await client.save_stream()
        #    except Exception as e:
        #        print(f"Error saving stream: {str(e)}")

        print("Stopping the VNC client...")
        try:
            browser.close()
        except Exception as e:
            print(f"Error stopping VNC client: {str(e)}")


def initialize_output_directory(directory_format):
    run_id = 1
    while os.path.exists(directory_format(run_id)):
        run_id += 1
    os.makedirs(directory_format(run_id), exist_ok=True)
    return directory_format(run_id)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", type=str, help="User prompt for the agent")
    args = parser.parse_args()

    output_dir = initialize_output_directory(lambda id: f"./output/run_{id}")
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start(user_input=args.prompt, output_dir=output_dir))
