"""Chapter 1: offline response inspection; --live opts into a paid API call."""
from __future__ import annotations

import argparse
import json
import os


def summarize(message: dict) -> dict:
    return {
        "text": "".join(b["text"] for b in message["content"] if b["type"] == "text"),
        "stop_reason": message.get("stop_reason"),
        "usage": message.get("usage", {}),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--stream", action="store_true")
    parser.add_argument("--max-tokens", type=int, default=512)
    args = parser.parse_args()
    if args.max_tokens < 1:
        parser.error("--max-tokens must be positive")
    if not args.live:
        print("OFFLINE: synthetic response, not model output or actual billing.")
        response = {
            "content": [{"type": "text", "text": "A model selects actions; a program executes them."}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 20, "output_tokens": 14},
        }
    else:
        if not os.getenv("ANTHROPIC_API_KEY") or not os.getenv("ANTHROPIC_MODEL"):
            raise SystemExit("Set ANTHROPIC_API_KEY and ANTHROPIC_MODEL privately first.")
        from anthropic import Anthropic

        request = {
            "model": os.environ["ANTHROPIC_MODEL"],
            "max_tokens": args.max_tokens,
            "system": "Explain programming concepts concisely in Chinese.",
            "messages": [{"role": "user", "content": "用一个例子说明模型与工具执行器的区别。"}],
        }
        # Retry only at this transport layer; no outer retry loop.
        with Anthropic(timeout=30.0, max_retries=2) as client:
            if args.stream:
                with client.messages.stream(**request) as stream:
                    for piece in stream.text_stream:
                        print(piece, end="", flush=True)
                    response = stream.get_final_message().model_dump(mode="json")
                print()
            else:
                response = client.messages.create(**request).model_dump(mode="json")
    print(json.dumps(summarize(response), ensure_ascii=False, indent=2))
    if response["stop_reason"] != "end_turn":
        print("Not a normal end_turn: inspect stop_reason before using this output.")


if __name__ == "__main__":
    main()
