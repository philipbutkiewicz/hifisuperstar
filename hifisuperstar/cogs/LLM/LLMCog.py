#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2026 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import re

import discord
from discord import app_commands
from discord.ext import commands
from httpx import AsyncClient
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI

from hifisuperstar.cogs.LLM.PromptTemplates.DefaultSystemPrompt import (
    default_system_prompt as _DEFAULT_SYS_PROMPT,
)
from hifisuperstar.cogs.LLM.PromptTemplates.EvilSystemPrompt import (
    evil_system_prompt as _EVIL_SYS_PROMPT,
)
from hifisuperstar.cogs.LLM.Tools.ImageSearchTool import search_images
from hifisuperstar.cogs.LLM.Tools.MusicTool import create_music_tools
from hifisuperstar.cogs.LLM.Tools.WebSearchTool import web_fetch, web_search
from hifisuperstar.core.Server.Events import Events
from hifisuperstar.core.Server.Server import check_server, respond
from hifisuperstar.io.Logger import error, info

_TOKEN_STRIP_RE = re.compile(r"<\|[^|]+\|>", re.DOTALL)
_THINK_RE = re.compile(r"<think>.*?</think>|<think>.*", re.DOTALL)


def _resolve_prompt(raw) -> str:
    """Resolve a prompt value that may be a string, tuple, or None."""
    if isinstance(raw, (list, tuple)):
        return " ".join(raw)
    return raw or ""


_STATIC_TOOLS = [search_images, web_search, web_fetch]


class LLMCog(commands.Cog):
    def __init__(self, config, bot):
        info(self, "Registered")
        self.config = config
        self.bot = bot
        self.guild_states = {}
        Events.add_event("on_message", self.on_message)

    def _default_state(self) -> dict:
        return {
            "enabled": False,
            "channel_id": None,
            "mode": "default",
            "sys_prompt": _resolve_prompt(
                self.config["LLMCog"].get("Sys_Prompt") or _DEFAULT_SYS_PROMPT
            ),
            "conversation_history": [],
            "model": self.config["LLMCog"]["OpenAI_API_Model"],
            "max_tokens": self.config["LLMCog"]["Max_Tokens"],
            "reasoning_effort": self.config["LLMCog"].get("Reasoning_Effort", "none"),
            "max_web_search_calls": int(
                self.config["LLMCog"].get("Max_Web_Search_Calls", 5)
            ),
        }

    def _get_state(self, guild_id) -> dict:
        if guild_id not in self.guild_states:
            self.guild_states[guild_id] = self._default_state()

        return self.guild_states[guild_id]

    def _build_llm(self, state) -> ChatOpenAI:
        kwargs = {
            "model": state["model"],
            "max_tokens": state["max_tokens"],
            "api_key": self.config["LLMCog"]["OpenAI_API_Key"],
            "base_url": self.config["LLMCog"]["OpenAI_API_URL"],
            "timeout": None,
        }
        reasoning_effort = state["reasoning_effort"]
        if reasoning_effort and reasoning_effort != "none":
            kwargs["model_kwargs"] = {"reasoning_effort": reasoning_effort}
        return ChatOpenAI(**kwargs)

    async def on_message(self, message):
        info(
            self,
            f"Message received {message if self.config['LLMCog']['Log_Messages'] else ''}",
        )

        if message.guild is None:
            return

        state = self._get_state(message.guild.id)

        if not state["enabled"]:
            return

        if message.author == message.guild.me:
            return

        if message.author.bot and message.guild.me not in message.mentions:
            return

        if (
            state["channel_id"] is not None
            and message.channel.id != state["channel_id"]
        ):
            return

        async with message.channel.typing():
            placeholder = await message.channel.send("🤔 Thinking...", reference=message)

            async def report_progress(text):
                try:
                    await placeholder.edit(content=text)
                except discord.HTTPException:
                    pass

            response, direct_posts = await self.generate_response(
                state,
                message,
                f"<@{message.author.display_name}> {message.content}",
                progress_callback=report_progress,
            )

        if response:
            chunks = [response[i : i + 1900] for i in range(0, len(response), 1900)]
            try:
                await placeholder.edit(content=chunks[0])
            except discord.HTTPException:
                await message.channel.send(chunks[0])
            for chunk in chunks[1:]:
                await message.channel.send(chunk)
        else:
            try:
                await placeholder.delete()
            except discord.HTTPException:
                pass
        for post in direct_posts:
            await message.channel.send(post)

    @app_commands.command(
        name="llm_set_channel",
        description="Sets the channel the LLM bot will respond in",
    )
    @app_commands.checks.has_role("Admin")
    async def set_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ):
        if not await check_server(interaction):
            return

        self._get_state(interaction.guild.id)["channel_id"] = channel.id
        await respond(interaction, f"LLM will now only respond in {channel.mention}!")

    @app_commands.command(
        name="llm_clear_channel",
        description="Removes the channel restriction so the LLM responds everywhere",
    )
    @app_commands.checks.has_role("Admin")
    async def clear_channel(self, interaction: discord.Interaction):
        if not await check_server(interaction):
            return

        self._get_state(interaction.guild.id)["channel_id"] = None
        await respond(interaction, "LLM channel restriction removed.")

    @app_commands.command(
        name="toggle_llm", description="Toggles LLM responses on or off"
    )
    @app_commands.checks.has_role("Admin")
    async def toggle_llm(self, interaction: discord.Interaction):
        if not await check_server(interaction):
            return

        state = self._get_state(interaction.guild.id)
        state["enabled"] = not state["enabled"]
        if not state["enabled"]:
            state["conversation_history"] = []

        await respond(
            interaction,
            f"LLM responses {'enabled' if state['enabled'] else 'disabled'}!",
        )

    @app_commands.command(name="llm_set_model_id", description="Sets the LLM model ID")
    @app_commands.checks.has_role("Admin")
    async def set_model_id(self, interaction: discord.Interaction, model_id: str):
        if not await check_server(interaction):
            return

        self._get_state(interaction.guild.id)["model"] = model_id
        await respond(interaction, f"LLM model ID set to `{model_id}`!")

    @app_commands.command(
        name="llm_context_clear", description="Clears the LLM conversation context"
    )
    async def context_clear(self, interaction: discord.Interaction):
        if not await check_server(interaction):
            return

        self._get_state(interaction.guild.id)["conversation_history"] = []
        await respond(interaction, "LLM conversation context cleared!")

    @app_commands.command(
        name="llm_toggle_mode",
        description="Toggles LLM response mode between default and evil",
    )
    @app_commands.checks.has_role("Admin")
    async def toggle_mode(self, interaction: discord.Interaction):
        if not await check_server(interaction):
            return

        state = self._get_state(interaction.guild.id)
        if state["mode"] == "default":
            state["mode"] = "evil"
            state["sys_prompt"] = _resolve_prompt(
                self.config["LLMCog"].get("Sys_Prompt") or _EVIL_SYS_PROMPT
            )
        else:
            state["mode"] = "default"
            state["sys_prompt"] = _resolve_prompt(
                self.config["LLMCog"].get("Sys_Prompt") or _DEFAULT_SYS_PROMPT
            )

        state["conversation_history"] = []
        await respond(
            interaction,
            f"LLM mode set to `{state['mode']}`. Conversation history cleared.",
        )

    @app_commands.command(
        name="llm_set_max_tokens",
        description="Sets the maximum number of tokens for LLM responses",
    )
    @app_commands.checks.has_role("Admin")
    async def set_max_tokens(self, interaction: discord.Interaction, max_tokens: int):
        if not await check_server(interaction):
            return

        if max_tokens < 1 or max_tokens > 16384:
            return await respond(
                interaction, "ERROR: max_tokens must be between 1 and 16384."
            )

        self._get_state(interaction.guild.id)["max_tokens"] = max_tokens
        await respond(interaction, f"LLM max tokens set to `{max_tokens}`!")

    @app_commands.command(
        name="llm_set_reasoning_effort", description="Sets the LLM reasoning effort"
    )
    @app_commands.checks.has_role("Admin")
    @app_commands.choices(
        effort=[
            app_commands.Choice(name="none", value="none"),
            app_commands.Choice(name="minimal", value="minimal"),
            app_commands.Choice(name="low", value="low"),
            app_commands.Choice(name="medium", value="medium"),
            app_commands.Choice(name="high", value="high"),
            app_commands.Choice(name="xhigh", value="xhigh"),
        ]
    )
    async def set_reasoning_effort(
        self, interaction: discord.Interaction, effort: app_commands.Choice[str]
    ):
        if not await check_server(interaction):
            return

        self._get_state(interaction.guild.id)["reasoning_effort"] = effort.value
        await respond(interaction, f"LLM reasoning effort set to `{effort.value}`!")

    @app_commands.command(
        name="llm_set_max_web_search_calls",
        description="Sets the max number of web search/fetch tool calls allowed per message",
    )
    @app_commands.checks.has_role("Admin")
    async def set_max_web_search_calls(
        self, interaction: discord.Interaction, max_calls: int
    ):
        if not await check_server(interaction):
            return

        if max_calls < 0 or max_calls > 25:
            return await respond(
                interaction, "ERROR: max_calls must be between 0 and 25."
            )

        self._get_state(interaction.guild.id)["max_web_search_calls"] = max_calls
        await respond(interaction, f"LLM max web search calls set to `{max_calls}`!")

    @app_commands.command(
        name="llm_list_models", description="Lists models available on the LLM API"
    )
    @app_commands.checks.has_role("Admin")
    async def list_models(self, interaction: discord.Interaction):
        if not await check_server(interaction):
            return

        async with AsyncClient(timeout=10) as client:
            try:
                response = await client.get(
                    f"{self.config['LLMCog']['OpenAI_API_URL']}/models",
                    headers={
                        "Authorization": f"Bearer {self.config['LLMCog']['OpenAI_API_Key']}"
                    },
                )
                response.raise_for_status()
                models = (
                    [m["id"] for m in response.json().get("data", [])]
                    if type(response.json()) is dict
                    else response.json()
                )
            except Exception as e:
                error(self, f"Failed to list models: {e}")
                return await respond(
                    interaction, "ERROR: Failed to fetch models from the API."
                )

        if not models:
            return await respond(interaction, "No models available.")

        if len(models) > 25:
            return await respond(
                interaction, f"{len(models)} models available. Too many to list!"
            )

        embed = discord.Embed(
            title="Available Models",
            description="\n".join(f"`{m}`" for m in models),
            color=discord.Color.blurple(),
        )
        embed.set_footer(
            text=f"{len(models)} model(s) — current: {self._get_state(interaction.guild.id)['model']}"
        )
        await respond(interaction, embed=embed)

    async def generate_response(
        self, state, message, message_text, progress_callback=None
    ) -> tuple:
        """Returns (response_text | None, direct_posts: list[str])."""

        async def report_progress(text):
            if progress_callback is None:
                return
            try:
                await progress_callback(text)
            except Exception as exc:
                error(self, f"Progress callback failed: {exc}")

        if len(state["conversation_history"]) > 64:
            state["conversation_history"] = state["conversation_history"][-64:]

        tools = list(_STATIC_TOOLS)
        music_cog = self.bot.get_cog("MusicCog")
        if music_cog is not None:
            tools.extend(create_music_tools(music_cog, message))
        else:
            info(self, "MusicCog not found, music tools will not be available")
        info(self, f"Tools available: {[t.name for t in tools]}")
        tools_by_name = {t.name: t for t in tools}

        llm = self._build_llm(state)
        llm_with_tools = llm.bind_tools(tools)

        tool_hint = (
            "You have access to the following tools: "
            + ", ".join(f"`{t.name}`" for t in tools)
            + ". Use them whenever the user asks for something they can do "
            "(e.g. playing music, searching images). Do not refuse or say the tools are unavailable — just call them."
        )

        lc_messages = [
            SystemMessage(content=state["sys_prompt"] + " " + tool_hint),
            *state["conversation_history"],
            HumanMessage(content=message_text),
        ]

        direct_posts = []
        web_sources = []
        web_tool_names = {"web_search", "web_fetch"}
        max_web_calls = state["max_web_search_calls"]
        web_call_count = 0

        try:
            while True:
                response_msg = await llm_with_tools.ainvoke(lc_messages)
                lc_messages.append(response_msg)

                info(
                    self,
                    f"LLM response: tool_calls={response_msg.tool_calls} content_preview={str(response_msg.content)[:120]!r}",
                )

                if not response_msg.tool_calls:
                    break

                for tc in response_msg.tool_calls:
                    info(self, f"Tool call: {tc['name']} args={tc['args']}")

                    if tc["name"] in web_tool_names:
                        web_call_count += 1
                        if web_call_count > max_web_calls:
                            warn_msg = (
                                f"Web search limit reached ({max_web_calls} calls per "
                                "message); answer using what you already know."
                            )
                            lc_messages.append(
                                ToolMessage(content=warn_msg, tool_call_id=tc["id"])
                            )
                            continue

                        await report_progress(
                            f"🌐 Searching the web ({web_call_count}/{max_web_calls})..."
                        )
                    else:
                        await report_progress(f"🔧 Using `{tc['name']}`...")

                    tool_fn = tools_by_name.get(tc["name"])
                    if tool_fn is None:
                        tool_result = f"Unknown tool: {tc['name']}"
                    else:
                        try:
                            tool_result = await tool_fn.ainvoke(tc["args"])
                        except Exception as te:
                            error(
                                self, f"Tool '{tc['name']}' raised an exception: {te}"
                            )
                            tool_result = f"Tool error: {te}"

                    if tc["name"] == "search_images":
                        for line in str(tool_result).splitlines():
                            if ": http" in line:
                                direct_posts.append(line.split(": ", 1)[1])

                    if tc["name"] == "web_fetch" and not str(tool_result).startswith(
                        "Failed to fetch"
                    ):
                        fetched_url = tc["args"].get("url")
                        if fetched_url and fetched_url not in web_sources:
                            web_sources.append(fetched_url)

                    lc_messages.append(
                        ToolMessage(content=str(tool_result), tool_call_id=tc["id"])
                    )

            await report_progress("✍️ Writing a reply...")
            content = response_msg.content or ""
            response_text = _THINK_RE.sub("", content).replace(
                ":eggplant:", "<:621331184676503554:1419337041921179648>"
            )
            response_text = _TOKEN_STRIP_RE.sub("", response_text).strip()

            if not response_text:
                return None, []

            if web_sources:
                sources_line = "-# Sources: " + " • ".join(
                    f"[{i}]({url})" for i, url in enumerate(web_sources[:5], start=1)
                )
                response_text = f"{response_text}\n{sources_line}"

            state["conversation_history"] += [
                HumanMessage(content=message_text),
                AIMessage(content=response_text),
            ]

            return response_text, direct_posts
        except Exception as e:
            error(self, f"Failed to generate LLM response: {e}")
            return None, []
