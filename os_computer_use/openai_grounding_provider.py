import os
import base64
from openai import OpenAI
from PIL import Image
from os_computer_use.logging import logger

class OpenAIGroundingProvider:
    """
    Uses GPT-4o vision to locate UI elements and return click coordinates.
    """

    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def call(self, prompt, image_data):
        with open(image_data, "rb") as f:
            b64_image = base64.b64encode(f.read()).decode("utf-8")

        image = Image.open(image_data)
        width, height = image.size

        response = self.client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are a UI element locator. The image is {width}x{height} pixels. "
                        "When asked to find a UI element, respond with ONLY the x,y pixel coordinates "
                        "of the center of that element. Format: x,y (just two numbers separated by a comma, nothing else)."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64_image}"},
                        },
                        {
                            "type": "text",
                            "text": f"Find the center coordinates of: {prompt}",
                        },
                    ],
                },
            ],
            max_tokens=50,
        )

        text = response.choices[0].message.content.strip()
        logger.log(f"grounding response: {text}", "gray")

        parts = [p.strip() for p in text.split(",")]
        x, y = float(parts[0]), float(parts[1])
        return x, y
