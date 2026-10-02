#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2026 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import asyncio
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from hifisuperstar.cogs.Acl.AclCog import AclCog
from hifisuperstar.cogs.LLM.LLMCog import LLMCog
from hifisuperstar.cogs.SelectableRoles.SelectableRolesCog import SelectableRolesCog
from hifisuperstar.cogs.UserJoin.UserJoinCog import UserJoinCog
from hifisuperstar.io.Resources import load_resource, save_resource


class GuildSettingsTests(unittest.TestCase):
    def setUp(self):
        self.previous_directory = os.getcwd()
        self.directory = tempfile.TemporaryDirectory()
        os.chdir(self.directory.name)
        os.mkdir("storage")

    def tearDown(self):
        os.chdir(self.previous_directory)
        self.directory.cleanup()

    def test_llm_commands_persist_only_their_guild_settings(self):
        config = {
            "LLMCog": {"OpenAI_API_Model": "default", "Max_Tokens": 100},
            "Guilds": {
                "33": {"LLMCog": {"OpenAI_API_Model": "local", "Max_Tokens": 200}}
            },
        }
        cog = LLMCog.__new__(LLMCog)
        cog.config = config
        cog.guild_states = {}
        first = SimpleNamespace(guild=SimpleNamespace(id=11))
        second = SimpleNamespace(guild=SimpleNamespace(id=22))
        channel = SimpleNamespace(id=101, mention="#chat")

        async def configure():
            with (
                patch(
                    "hifisuperstar.cogs.LLM.LLMCog.check_server",
                    new=AsyncMock(return_value=True),
                ),
                patch("hifisuperstar.cogs.LLM.LLMCog.respond", new=AsyncMock()),
            ):
                await LLMCog.set_channel.callback(cog, first, channel)
                await LLMCog.toggle_llm.callback(cog, first)
                await LLMCog.set_model_id.callback(cog, first, "custom")
                await LLMCog.set_max_tokens.callback(cog, first, 256)
                await LLMCog.set_reasoning_effort.callback(
                    cog, first, SimpleNamespace(value="high")
                )
                await LLMCog.set_max_web_search_calls.callback(cog, first, 3)
                await LLMCog.toggle_mode.callback(cog, first)
                await LLMCog.set_channel.callback(
                    cog, second, SimpleNamespace(id=202, mention="#other")
                )
                await LLMCog.clear_channel.callback(cog, second)
                await LLMCog.toggle_llm.callback(cog, second)
                await LLMCog.toggle_llm.callback(cog, second)

        asyncio.run(configure())
        cog._get_state(11)["conversation_history"].append("temporary")
        assert "conversation_history" not in load_resource("llm", 11)
        cog.guild_states = {}
        first_state = cog._get_state(11)
        second_state = cog._get_state(22)
        self.assertEqual(first_state["channel_id"], 101)
        self.assertTrue(first_state["enabled"])
        self.assertEqual(first_state["model"], "custom")
        self.assertEqual(first_state["max_tokens"], 256)
        self.assertEqual(first_state["reasoning_effort"], "high")
        self.assertEqual(first_state["max_web_search_calls"], 3)
        self.assertEqual(first_state["mode"], "evil")
        self.assertEqual(first_state["conversation_history"], [])
        self.assertIsNone(second_state["channel_id"])
        self.assertFalse(second_state["enabled"])
        self.assertEqual(second_state["model"], "default")
        self.assertEqual(cog._get_state(33)["model"], "local")
        self.assertEqual(cog._get_state(33)["max_tokens"], 200)

    def test_llm_api_credentials_are_selected_by_guild(self):
        cog = LLMCog.__new__(LLMCog)
        cog.config = {
            "LLMCog": {
                "OpenAI_API_Key": "default",
                "OpenAI_API_URL": "https://default",
            },
            "Guilds": {
                "22": {
                    "LLMCog": {
                        "OpenAI_API_Key": "other",
                        "OpenAI_API_URL": "https://other",
                    }
                }
            },
        }
        state = {"model": "model", "max_tokens": 100, "reasoning_effort": "none"}
        with patch("hifisuperstar.cogs.LLM.LLMCog.ChatOpenAI") as llm:
            cog._build_llm(state, 11)
            self.assertEqual(llm.call_args.kwargs["api_key"], "default")
            cog._build_llm(state, 22)
            self.assertEqual(llm.call_args.kwargs["api_key"], "other")
            self.assertEqual(llm.call_args.kwargs["base_url"], "https://other")

    def test_user_join_uses_its_guild_channel(self):
        save_resource("userjoin", 11, {"channel": "welcome", "enabled": True})
        save_resource("userjoin", 22, {"channel": "welcome", "enabled": False})
        sent = []
        channel = SimpleNamespace(
            name="welcome", send=lambda text: asyncio.sleep(0, result=sent.append(text))
        )
        guild = SimpleNamespace(id=11, name="One", text_channels=[channel])
        member = SimpleNamespace(guild=guild)
        cog = UserJoinCog.__new__(UserJoinCog)

        asyncio.run(cog.on_member_join(member))
        member.guild = SimpleNamespace(id=22, name="Two", text_channels=[channel])
        asyncio.run(cog.on_member_join(member))

        self.assertEqual(len(sent), 1)
        self.assertIn("has joined the server", sent[0])

    def test_reaction_uses_roles_and_message_from_its_guild(self):
        save_resource("selectableroles", 11, {"default": {"DJ": {"emoji": "🎵"}}})
        save_resource("selectableroles", 22, {"default": {"Other": {"emoji": "🎵"}}})
        save_resource("messageids", 11, {"900": "default"})
        role = SimpleNamespace(name="DJ")
        guild = SimpleNamespace(id=11, name="One", roles=[role])
        message = SimpleNamespace(id=900, guild=guild, author=SimpleNamespace(bot=True))
        reaction = SimpleNamespace(message=message, emoji=SimpleNamespace(name="🎵"))
        member = SimpleNamespace(
            bot=False, remove_roles=AsyncMock(), add_roles=AsyncMock()
        )
        cog = SelectableRolesCog.__new__(SelectableRolesCog)
        cog.selectable_roles = {}
        cog.message_ids = {}

        asyncio.run(cog.on_reaction_add(reaction, member))

        member.add_roles.assert_awaited_once_with(role)
        message.guild = SimpleNamespace(
            id=22, name="Two", roles=[SimpleNamespace(name="Other")]
        )
        asyncio.run(cog.on_reaction_add(reaction, member))
        member.add_roles.assert_awaited_once_with(role)

    def test_acl_commands_save_only_their_guild_rules(self):
        cog = AclCog.__new__(AclCog)
        member = SimpleNamespace(id=123)

        async def run():
            with (
                patch(
                    "hifisuperstar.cogs.Acl.AclCog.check_server",
                    new=AsyncMock(return_value=True),
                ),
                patch("hifisuperstar.cogs.Acl.AclCog.respond", new=AsyncMock()),
            ):
                await AclCog.set_rule.callback(
                    cog,
                    SimpleNamespace(guild=SimpleNamespace(id=11, name="One")),
                    "PLAY",
                    "0",
                    member,
                )
                await AclCog.admin_mode.callback(
                    cog, SimpleNamespace(guild=SimpleNamespace(id=22, name="Two"))
                )

        asyncio.run(run())
        self.assertEqual(load_resource("acl", 11)["123"]["PLAY"], "0")
        self.assertNotIn("ADMIN_MODE", load_resource("acl", 11))
        self.assertEqual(load_resource("acl", 22), {"ADMIN_MODE": True})

    def test_user_join_channel_commands_save_per_guild(self):
        cog = UserJoinCog.__new__(UserJoinCog)

        def request(guild_id, channel):
            return SimpleNamespace(
                guild=SimpleNamespace(
                    id=guild_id,
                    name=str(guild_id),
                    text_channels=[SimpleNamespace(name=channel)],
                )
            )

        async def run():
            with (
                patch(
                    "hifisuperstar.cogs.UserJoin.UserJoinCog.check_server",
                    new=AsyncMock(return_value=True),
                ),
                patch(
                    "hifisuperstar.cogs.UserJoin.UserJoinCog.respond", new=AsyncMock()
                ),
            ):
                await UserJoinCog.set_userjoin_channel.callback(
                    cog, request(11, "welcome"), "welcome"
                )
                await UserJoinCog.set_userjoin_channel.callback(
                    cog, request(22, "lobby"), "lobby"
                )
                await UserJoinCog.disable_userjoin.callback(cog, request(22, "lobby"))

        asyncio.run(run())
        self.assertEqual(
            load_resource("userjoin", 11), {"channel": "welcome", "enabled": True}
        )
        self.assertFalse(load_resource("userjoin", 22)["enabled"])

    def test_selectable_role_command_saves_only_its_guild(self):
        cog = SelectableRolesCog.__new__(SelectableRolesCog)
        cog.selectable_roles = {}
        cog.message_ids = {}
        role = SimpleNamespace(name="DJ")
        message = SimpleNamespace(id=900, add_reaction=AsyncMock())
        request = SimpleNamespace(
            guild=SimpleNamespace(id=11, name="One", roles=[role]),
            original_response=AsyncMock(return_value=message),
        )

        async def run():
            with (
                patch(
                    "hifisuperstar.cogs.SelectableRoles.SelectableRolesCog.check_server",
                    new=AsyncMock(return_value=True),
                ),
                patch(
                    "hifisuperstar.cogs.SelectableRoles.SelectableRolesCog.respond",
                    new=AsyncMock(),
                ),
            ):
                await SelectableRolesCog.add_selectable_role.callback(
                    cog, request, "DJ", "🎵"
                )
                await SelectableRolesCog.selectable_roles.callback(cog, request)

        asyncio.run(run())
        self.assertEqual(
            load_resource("selectableroles", 11), {"default": {"DJ": {"emoji": "🎵"}}}
        )
        self.assertEqual(load_resource("selectableroles", 22), {})
        self.assertEqual(load_resource("messageids", 11), {"900": "default"})
        self.assertEqual(load_resource("messageids", 22), {})
        message.add_reaction.assert_awaited_once_with("🎵")


if __name__ == "__main__":
    unittest.main()
