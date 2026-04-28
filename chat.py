"""Simple CLI chat demo that shows memory across turns.

Usage:
    python chat.py

The agent remembers what you said in previous turns via SimpleMemory.
Type 'quit' or 'exit' to stop. Type 'clear' to wipe memory.
"""

import asyncio
import os

from dotenv import load_dotenv
from openai import OpenAI

from memory.simple import SimpleMemory

load_dotenv(override=True)

API_BASE = "https://api2.aigcbest.top/v1"
API_KEY = "sk-yt5aRPe0nbvUQXXyjBPpdqLdomofDTwSCPgQy4giYdnXAyLq"

SYSTEM_PROMPT = (
    "You are a friendly conversational assistant. "
    "When the user refers to something they mentioned earlier, use the conversation history."
)


async def chat():
    memory = SimpleMemory(max_turns=20)
    client = OpenAI(api_key=API_KEY, base_url=API_BASE)

    print("Chat started. Type 'quit' to exit, 'clear' to reset memory.\n")

    # Track current session messages (without injected memory)
    session_messages: list[dict] = []

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit"):
            print("Bye!")
            break
        if user_input.lower() == "clear":
            await memory.clear()
            session_messages.clear()
            print("[Memory cleared]\n")
            continue

        # Store user turn
        await memory.store("user", user_input)
        session_messages.append({"role": "user", "content": user_input})

        # Build messages: system + injected memory + current session
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        memory_text = await memory.retrieve()
        if memory_text:
            messages.append({"role": "system", "content": memory_text})

        messages.extend(session_messages)

        # Call LLM
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
        )
        reply = response.choices[0].message.content.strip()

        # Store assistant turn
        await memory.store("assistant", reply)
        session_messages.append({"role": "assistant", "content": reply})

        print(f"Assistant: {reply}\n")


if __name__ == "__main__":
    asyncio.run(chat())
