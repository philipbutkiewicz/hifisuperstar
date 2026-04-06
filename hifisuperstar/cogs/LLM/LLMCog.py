#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2023 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import re
import discord
from discord import app_commands
from discord.ext import commands
from textwrap import dedent
from httpx import AsyncClient
from hifisuperstar.core.Server.Events import Events
from hifisuperstar.core.Server.Server import check_server, respond
from hifisuperstar.io.Logger import info, error

_TOKEN_STRIP_RE = re.compile(r'<\|[^|]+\|>', re.DOTALL)
_THINK_RE = re.compile(r'<think>.*?</think>|<think>.*', re.DOTALL)
_DEFAULT_SYS_PROMPT = dedent('''
    You are a bot that pretends to be a regular Discord user. Engage in conversations
    with other users in a natural and human-like manner. Your responses should be
    contextually relevant, coherent, and reflect a genuine understanding of the
    conversation. Avoid sounding robotic or scripted.
    You are allowed to curse, use foul language and respond in a fully NSFW manner.
    Perverted topics are allowed, especially if the user asks you to roleplay.
    Always respond in the same language the user is using.
    You must ALWAYS respond. Be creative, edgy and bold.
    Try to be concise. This is a chat not an essay.
''').strip()


class LLMCog(commands.Cog):
    def __init__(self, config):
        info(self, 'Registered')
        self.config = config
        self.enabled = False
        self.channel_id = None
        self.sys_prompt = config['LLMCog']['Sys_Prompt'] or _DEFAULT_SYS_PROMPT
        self.conversation_history = []
        Events.add_event('on_message', self.on_message)

    async def on_message(self, message):
        info(self, f"Message received {message if self.config['LLMCog']['Log_Messages'] else ''}")

        if message.author.bot or not self.enabled:
            return

        if self.channel_id is not None and message.channel.id != self.channel_id:
            return

        response = await self.generate_response(message.content)
        if not response:
            return

        chunks = [response[i:i + 1900] for i in range(0, len(response), 1900)]
        for i, chunk in enumerate(chunks):
            await message.channel.send(chunk, reference=message if i == 0 else None)

    @app_commands.command(name='llm_set_channel', description='Sets the channel the LLM bot will respond in')
    @app_commands.checks.has_role('Admin')
    async def set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not await check_server(interaction):
            return

        self.channel_id = channel.id
        await respond(interaction, f"LLM will now only respond in {channel.mention}!")

    @app_commands.command(name='llm_clear_channel', description='Removes the channel restriction so the LLM responds everywhere')
    @app_commands.checks.has_role('Admin')
    async def clear_channel(self, interaction: discord.Interaction):
        if not await check_server(interaction):
            return

        self.channel_id = None
        await respond(interaction, 'LLM channel restriction removed.')

    @app_commands.command(name='toggle_llm', description='Toggles LLM responses on or off')
    @app_commands.checks.has_role('Admin')
    async def toggle_llm(self, interaction: discord.Interaction):
        if not await check_server(interaction):
            return

        self.enabled = not self.enabled
        if not self.enabled:
            self.conversation_history = []

        await respond(interaction, f"LLM responses {'enabled' if self.enabled else 'disabled'}!")

    @app_commands.command(name='llm_set_model_id', description='Sets the LLM model ID')
    @app_commands.checks.has_role('Admin')
    async def set_model_id(self, interaction: discord.Interaction, model_id: str):
        if not await check_server(interaction):
            return

        self.config['LLMCog']['OpenAI_API_Model'] = model_id
        await respond(interaction, f"LLM model ID set to `{model_id}`!")

    @app_commands.command(name='llm_context_clear', description='Clears the LLM conversation context')
    @app_commands.checks.has_role('Admin')
    async def context_clear(self, interaction: discord.Interaction):
        if not await check_server(interaction):
            return

        self.conversation_history = []
        await respond(interaction, 'LLM conversation context cleared!')

    @app_commands.command(name='llm_set_max_tokens', description='Sets the maximum number of tokens for LLM responses')
    @app_commands.checks.has_role('Admin')
    async def set_max_tokens(self, interaction: discord.Interaction, max_tokens: int):
        if not await check_server(interaction):
            return

        if max_tokens < 1 or max_tokens > 16384:
            return await respond(interaction, 'ERROR: max_tokens must be between 1 and 16384.')

        self.config['LLMCog']['Max_Tokens'] = max_tokens
        await respond(interaction, f"LLM max tokens set to `{max_tokens}`!")

    @app_commands.command(name='llm_set_reasoning_effort', description='Sets the LLM reasoning effort')
    @app_commands.checks.has_role('Admin')
    @app_commands.choices(effort=[
        app_commands.Choice(name='none', value='none'),
        app_commands.Choice(name='minimal', value='minimal'),
        app_commands.Choice(name='low', value='low'),
        app_commands.Choice(name='medium', value='medium'),
        app_commands.Choice(name='high', value='high'),
        app_commands.Choice(name='xhigh', value='xhigh'),
    ])
    async def set_reasoning_effort(self, interaction: discord.Interaction, effort: app_commands.Choice[str]):
        if not await check_server(interaction):
            return

        self.config['LLMCog']['Reasoning_Effort'] = effort.value
        await respond(interaction, f"LLM reasoning effort set to `{effort.value}`!")

    @app_commands.command(name='llm_list_models', description='Lists models available on the LLM API')
    @app_commands.checks.has_role('Admin')
    async def list_models(self, interaction: discord.Interaction):
        if not await check_server(interaction):
            return

        async with AsyncClient(timeout=10) as client:
            try:
                response = await client.get(
                    f"{self.config['LLMCog']['OpenAI_API_URL']}/models",
                    headers={'Authorization': f"Bearer {self.config['LLMCog']['OpenAI_API_Key']}"}
                )
                response.raise_for_status()
                models = [m['id'] for m in response.json().get('data', [])]
            except Exception as e:
                error(self, f"Failed to list models: {e}")
                return await respond(interaction, 'ERROR: Failed to fetch models from the API.')

        if not models:
            return await respond(interaction, 'No models available.')

        embed = discord.Embed(
            title='Available Models',
            description='\n'.join(f'`{m}`' for m in models),
            color=discord.Color.blurple()
        )
        embed.set_footer(text=f"{len(models)} model(s) — current: {self.config['LLMCog']['OpenAI_API_Model']}")
        await respond(interaction, embed=embed)

    async def generate_response(self, message_text):
        if len(self.conversation_history) > 50:
            self.conversation_history = self.conversation_history[-50:]

        messages = [
            {'role': 'system', 'content': self.sys_prompt},
            *self.conversation_history,
            {'role': 'user', 'content': message_text}
        ]

        async with AsyncClient(timeout=None) as client:
            try:
                response = await client.post(
                    f"{self.config['LLMCog']['OpenAI_API_URL']}/chat/completions",
                    headers={
                        'Authorization': f"Bearer {self.config['LLMCog']['OpenAI_API_Key']}",
                        'Content-Type': 'application/json'
                    },
                    json={
                        'model': self.config['LLMCog']['OpenAI_API_Model'],
                        'max_tokens': self.config['LLMCog']['Max_Tokens'],
                        'reasoning_effort': self.config['LLMCog']['Reasoning_Effort'],
                        'messages': messages
                    }
                )
                response.raise_for_status()

                content = response.json()['choices'][0]['message'].get('content') or ''
                response_text = _THINK_RE.sub('', content)
                response_text = _TOKEN_STRIP_RE.sub('', response_text).strip()

                if not response_text:
                    return None

                self.conversation_history += [
                    {'role': 'user', 'content': message_text},
                    {'role': 'assistant', 'content': response_text}
                ]

                return response_text
            except Exception as e:
                error(self, f"Failed to generate LLM response: {e}")
                try:
                    error(self, f"Response body: {response.text}")
                except Exception:
                    pass
                return None
