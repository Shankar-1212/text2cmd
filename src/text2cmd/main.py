#!/usr/bin/env python

import os
import subprocess
import typer
from dotenv import load_dotenv
import google.generativeai as genai
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
import json
import re

app = typer.Typer()
console = Console()

DANGEROUS_PATTERNS = [
    r"\brm\s+(-[a-zA-Z]*r|-[a-zA-Z]*f)",  # Matches 'rm -rf', 'rm -r -f', 'rm -fr' etc.
    r"\bdd\b",                           # Matches 'dd' command (can wipe disks)
    r"\bmkfs\b",                         # Matches 'mkfs' (format) commands
    r"\bfdisk\b",                        # Matches 'fdisk' (disk partitioner)
    r"\bgdisk\b",                        # Matches 'gdisk' (disk partitioner)
    r"\bparted\b",                       # Matches 'parted' (disk partitioner)
    r"\bshred\b",                        # Matches 'shred' (securely delete files, making them unrecoverable)
    r">[ \t]*/dev/sd[a-z]",              # Matches redirection to a disk device (e.g., > /dev/sda)

    r"\bsudo\b",                         # Matches 'sudo', as many dangerous commands require it
    r"\bchmod\b.*(777|-R)",              # Matches 'chmod' when used recursively or setting '777' permissions
    r"\bchown\b.*-R",                    # Matches 'chown' (change ownership) when used recursively
    r"\bmv\b.*\s/dev/null",              # Matches moving something to /dev/null (black hole, effective deletion)
    r"mv\s+.*\s+/etc",                   # Matches moving files into critical /etc directory
    r"mv\s+.*\s+/boot",                  # Matches moving files into critical /boot directory

    # --- Potentially Unsafe Remote Execution ---
    r"wget .* \| sh",                    # Matches downloading and executing a script with wget
    r"curl .* \| sh",                    # Matches downloading and executing a script with curl
    r"bash < /dev/tcp/",                 # Matches reverse shell attempts
    r"\bnc\b|\bnetcat\b",                # Matches 'nc' or 'netcat', often used for network connections/listeners
    
    # --- Process and Service Management ---
    r"\bkill\s+-9\b",                    # Matches 'kill -9' (SIGKILL), which can corrupt data if used improperly
    r"\bpkill\s+-9\b",                   # Matches 'pkill -9' (SIGKILL)
    
    # --- Obfuscated or Hidden Execution ---
    r"base64\s+--decode\s+\|",           # Matches base64 decoding piped to another command (often a shell)
    r"eval\b",                           # Matches 'eval', which can execute strings as commands
    r"\$\(.*\)",                         # Matches command substitution, which can hide commands inside others

    # --- Kernel and System Control ---
    r"sysctl\s+-w",                      # Matches 'sysctl -w' used to change kernel parameters at runtime
    r"echo\s+.\s+>\s+/proc/sys",          # Matches direct writing to kernel configuration via /proc
]


# --- API Key Configuration ---
load_dotenv()

try:
    api_key = os.environ["GEMINI_API_KEY"]
    if not api_key:
        raise KeyError
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')
except KeyError:
    console.print(
        Markdown(
            "**Error:** `GEMINI_API_KEY` not found or is empty. Please create a `.env` file "
            "in your project root and add `GEMINI_API_KEY=YOUR_API_KEY`."
        )
    )
    raise typer.Exit(code=1)
except Exception as e:
    console.print(Markdown(f"**An unexpected error occurred during Gemini API configuration:** {e}"))
    raise typer.Exit(code=1)


def generate_command(prompt: str) -> dict:
    """
    Sends the user's natural language prompt to the Gemini API and returns
    a dictionary containing the generated shell command and its explanation.
    """
    try:
        # We engineer the prompt to be very specific, asking for a JSON object.
        # This makes the output structured and predictable.
        full_prompt = f"""
        Given the following natural language task, provide a JSON object with two keys: "command" and "explanation".
        The "command" should be the corresponding shell command for a '{os.name}' operating system.
        The "explanation" should be a brief, one-sentence description of what the command does.
        Do not include any other text or formatting outside of the JSON object.

        Task: "{prompt}"
        """
        response = model.generate_content(full_prompt)
        cleaned_response = response.text.strip().replace("```json", "").replace("```", "")      
        result = json.loads(cleaned_response)
        
        if "command" not in result or "explanation" not in result:
            raise ValueError("The API response was missing 'command' or 'explanation'.")
            
        return result

    except json.JSONDecodeError:
        console.print(Markdown("**Error:** Could not parse the API response. The model may have returned an unexpected format."))
        return {}
    except Exception as e:
        console.print(Markdown(f"**Error generating command from Gemini API:** {e}"))
        return {}

def is_dangerous(command: str) -> bool:
    """
    Checks if a generated command matches any of the defined dangerous patterns.
    """
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command):
            return True
    return False

@app.command()
def ask(
    prompt: str = typer.Argument(..., help="The natural language task you want to convert to a command."),
    execute: bool = typer.Option(
        False,
        "--execute",
        "-e",
        help="Execute the generated command immediately without confirmation.",
    ),
):
    """
    Translates your natural language query into a shell command using the Gemini API.
    """
    if not prompt:
        console.print(Markdown("**Error:** Please provide a task to perform."))
        raise typer.Exit(code=1)

    with console.status("[bold green]Asking Gemini to generate command...[/bold green]"):
        response_data = generate_command(prompt)

    if not response_data:
        raise typer.Exit(code=1)

    generated_command = response_data.get("command", "")
    explanation = response_data.get("explanation", "No explanation provided.")

    console.print(
        Panel(
            f"[bold cyan]> {generated_command}[/bold cyan]\n\n[dim italic]{explanation}[/dim italic]",
            title="✨ Generated Command",
            border_style="green",
            expand=False
        )
    )

    if is_dangerous(generated_command):
        console.print(
            Panel(
                "[bold]This command is flagged as potentially destructive.[/bold]\n"
                "Please review it carefully before executing.",
                title="🚨 Safety Warning",
                border_style="bold red"
            )
        )

    should_execute = execute

    if not execute:
        should_execute = typer.confirm("Do you want to execute this command?")

    if should_execute:
        try:
            console.print(Markdown(f"---"))
            subprocess.run(generated_command, shell=True, check=True)
            console.print(Markdown(f"---"))
            console.print(Markdown("✅ **Command executed successfully.**"))
        except subprocess.CalledProcessError as e:
            console.print(Markdown(f"**Error executing command:** The command exited with status code {e.returncode}."))
        except Exception as e:
            console.print(Markdown(f"**An unexpected error occurred during execution:** {e}"))

if __name__ == "__main__":
    app()