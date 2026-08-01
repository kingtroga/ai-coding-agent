import os
import sys
import json
import argparse
import datetime

from google import genai
from google.genai import types

from agent_core import SYSTEM_PROMPT, MAX_TOOL_ITERATIONS, dispatch_tool

from dotenv import load_dotenv
load_dotenv()

MODEL = os.environ.get("AGENT_MODEL", "gemini-2.5-flash")

_STRING = types.Schema(type=types.Type.STRING)

FUNCTION_DECLARATIONS = [
    types.FunctionDeclaration(
        name="list_directory",
        description="List files and folders under a path in the repository, recursively (skips .git/node_modules/etc). Use this first to understand project layout.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={"path": types.Schema(type=types.Type.STRING, description="Path relative to the repo root. Use '.' for the repo root.")},
            required=["path"],
        ),
    ),
    types.FunctionDeclaration(
        name="read_file",
        description="Read a file's full contents with line numbers, relative to the repo root.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={"path": types.Schema(type=types.Type.STRING, description="File path relative to the repo root.")},
            required=["path"],
        ),
    ),
    types.FunctionDeclaration(
        name="search_code",
        description="Search all files for a literal text pattern (like grep), returning matching file:line:content. Optionally filter by filename glob, e.g. '*.js'.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "pattern": types.Schema(type=types.Type.STRING, description="Literal text to search for."),
                "glob": types.Schema(type=types.Type.STRING, description="Optional filename glob filter, e.g. '*.js'. Defaults to all files."),
            },
            required=["pattern"],
        ),
    ),
    types.FunctionDeclaration(
        name="write_file",
        description="Create a new file or overwrite an existing file with the given full content, relative to the repo root. Always read_file first if the file already exists, so you don't clobber unrelated content.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "path": types.Schema(type=types.Type.STRING, description="File path relative to the repo root."),
                "content": types.Schema(type=types.Type.STRING, description="The complete new content of the file."),
            },
            required=["path", "content"],
        ),
    ),
    types.FunctionDeclaration(
        name="run_command",
        description="Run a shell command with working directory set to the repo root. Use only for validation (e.g. 'node --check app/routes/note.routes.js'), not for installing large toolchains.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={"command": types.Schema(type=types.Type.STRING, description="Shell command to run.")},
            required=["command"],
        ),
    ),
]


def run_agent(repo_root: str, request: str, log_path: str = None) -> str:
    """Run the full explore -> plan -> implement -> summarize loop."""
    client = genai.Client()  # reads GEMINI_API_KEY (or GOOGLE_API_KEY) from env
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=[types.Tool(function_declarations=FUNCTION_DECLARATIONS)],
    )
    chat = client.chats.create(model=MODEL, config=config)

    transcript = []
    message = request

    for iteration in range(1, MAX_TOOL_ITERATIONS + 1):
        response = chat.send_message(message)
        candidate = response.candidates[0]
        parts = candidate.content.parts or []

        function_calls = [p.function_call for p in parts if getattr(p, "function_call", None)]
        text_parts = [p.text for p in parts if getattr(p, "text", None)]

        for text in text_parts:
            print(text)
            transcript.append({"role": "assistant", "text": text})

        if not function_calls:
            break  # model gave its final answer, no more tool calls

        response_parts = []
        for call in function_calls:
            call_args = dict(call.args) if call.args else {}
            print(f"\n[tool call] {call.name}({json.dumps(call_args)[:200]})")
            result = dispatch_tool(repo_root, call.name, call_args)
            print(f"[tool result] {result[:500]}{'...' if len(result) > 500 else ''}\n")
            transcript.append({"role": "tool", "name": call.name, "input": call_args, "result": result})
            response_parts.append(
                types.Part.from_function_response(name=call.name, response={"result": result})
            )

        message = response_parts
    else:
        print("\n[agent] Reached max tool-call iterations; stopping.")

    if log_path:
        with open(log_path, "w", encoding="utf-8") as fh:
            json.dump(transcript, fh, indent=2)
        print(f"\n[agent] Full transcript saved to {log_path}")

    return "\n".join(t["text"] for t in transcript if t["role"] == "assistant")


def main():
    parser = argparse.ArgumentParser(description="Gemini-backed coding agent for an existing repository.")
    parser.add_argument("repo_path", help="Path to the target repository on disk.")
    parser.add_argument("request", help="Plain-English product request.")
    parser.add_argument("--log", default=None, help="Path to save a JSON transcript. Defaults to agent_run_<timestamp>.json")
    args = parser.parse_args()

    if not os.path.isdir(args.repo_path):
        sys.exit(f"Repository path not found: {args.repo_path}")
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        sys.exit("Set GEMINI_API_KEY in your environment before running the agent.")

    log_path = args.log or f"agent_run_{datetime.datetime.now():%Y%m%d_%H%M%S}.json"
    print(f"[agent] Target repo: {os.path.abspath(args.repo_path)}")
    print(f"[agent] Request: {args.request}\n")

    run_agent(args.repo_path, args.request, log_path=log_path)


if __name__ == "__main__":
    main()
