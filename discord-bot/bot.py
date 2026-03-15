import argparse
import asyncio
import os
import re
import subprocess

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DISCORD_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID")

# Parse CLI args
parser = argparse.ArgumentParser()
parser.add_argument("-qq", action="store_true", help="Use qq instead of opencode")
parser.add_argument("-bedrock", action="store_true", help="Use Claude Agent SDK via Bedrock")
cli_args = parser.parse_args()
USE_QQ = cli_args.qq
USE_BEDROCK = cli_args.bedrock

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


def filter_output(text: str) -> str:
    """Clean up backend output: remove think tags, verification JSON, source citations."""
    # Remove </think> and everything before the last occurrence
    idx = text.rfind("</think>")
    if idx != -1:
        text = text[idx + len("</think>"):]
    # Strip any remaining <think> open tags
    text = re.sub(r"<think>", "", text)
    # Remove verification JSON blocks like {"pass": true, ...}
    text = re.sub(r"\{[^}]*\"pass\"\s*:.*?\}", "", text)
    # Remove "Assistant:" prefix
    text = re.sub(r"^Assistant:\s*", "", text.strip())
    # Remove trailing "Sources:" block (qq knowledge citations)
    text = re.sub(r"\nSources:.*", "", text, flags=re.DOTALL)
    # Remove "Shell cwd was reset" lines
    text = re.sub(r"Shell cwd was reset to.*", "", text)
    return text.strip()


async def run_backend(message: str) -> str:
    """Run the configured backend and return the filtered response."""
    if USE_BEDROCK:
        from bedrock_backend import run_bedrock

        return await run_bedrock(message)

    # Clear VIRTUAL_ENV so subprocesses use their own environments
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    cwd = None

    if USE_QQ:
        cmd = ["qq", "-m", message]
        # qq's MCP server needs to run from the qq project directory
        cwd = os.path.expanduser("~/git/autonomous-intelligence/qq")
    else:
        cmd = ["opencode", "run", message]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=cwd,
    )
    stdout, stderr = await proc.communicate()
    output = stdout.decode(errors="replace")
    # Strip ANSI escape codes
    output = re.sub(r"\x1b\[[0-9;]*m", "", output)
    return filter_output(output)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    if DISCORD_CHANNEL_ID:
        channel = bot.get_channel(int(DISCORD_CHANNEL_ID))
        if channel:
            print(f"Default channel: #{channel.name}")


@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return

    # If the bot is mentioned, reply with a greeting via opencode
    if bot.user in message.mentions:
        async with message.channel.typing():
            # Strip the mention from the message to get the actual content
            content = message.content.replace(f"<@{bot.user.id}>", "").strip()
            if not content:
                content = f"Greet the user '{message.author.display_name}' in a friendly way."
            response = await run_backend(content)
            if response:
                # Split long messages into 2000-char chunks (Discord limit)
                for chunk in split_message(response):
                    await message.reply(chunk)
            else:
                await message.reply("I got an empty response. Something may have gone wrong.")
        return

    await bot.process_commands(message)


@bot.command(name="ask")
async def ask(ctx: commands.Context, *, question: str):
    """Ask opencode a question and get a reply."""
    async with ctx.typing():
        response = await run_backend(question)
        if response:
            for chunk in split_message(response):
                await ctx.reply(chunk)
        else:
            await ctx.reply("I got an empty response. Something may have gone wrong.")


@bot.command(name="send")
async def send(ctx: commands.Context, channel_id: int, *, message: str):
    """Run opencode with a message and send the reply to a specific channel."""
    channel = bot.get_channel(channel_id)
    if not channel:
        await ctx.reply(f"Channel {channel_id} not found.")
        return

    async with ctx.typing():
        response = await run_backend(message)
        if response:
            for chunk in split_message(response):
                await channel.send(chunk)
            await ctx.reply(f"Response sent to <#{channel_id}>.")
        else:
            await ctx.reply("I got an empty response. Something may have gone wrong.")


def split_message(text: str, limit: int = 2000) -> list[str]:
    """Split text into chunks that fit within Discord's message limit."""
    chunks = []
    while len(text) > limit:
        # Try to split at a newline
        split_at = text.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = limit
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    if text:
        chunks.append(text)
    return chunks


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("Error: DISCORD_TOKEN not set in .env")
        exit(1)
    if USE_BEDROCK:
        backend = "bedrock"
    elif USE_QQ:
        backend = "qq"
    else:
        backend = "opencode"
    print(f"Using backend: {backend}")
    bot.run(DISCORD_TOKEN)
