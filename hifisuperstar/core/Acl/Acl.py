#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2026 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#
from hifisuperstar.io.Logger import warn
from hifisuperstar.io.Resources import load_resource, save_resource


TRUTHY = ("1", "true", "yes", "on")
FALSY = ("0", "false", "no", "off")
ADMIN_ROLE = "Admin"


def get_valid_rules():
    from hifisuperstar.core.Acl import Rule

    return sorted(
        value for key, value in vars(Rule).items() if key.isupper() and isinstance(value, str)
    )


def normalize_allowed(value):
    """Maps user input like 'true'/'0' to the stored '1'/'0' form, or None when it is not understood."""
    value = str(value).strip().lower()
    if value in TRUTHY:
        return "1"
    if value in FALSY:
        return "0"
    return None


class Acl:
    def __init__(self, guild_id):
        self.guild_id = guild_id
        self.rules = load_resource("acl", self.guild_id)

    def save_rules(self):
        save_resource("acl", self.guild_id, self.rules)

    def clear(self):
        self.rules = {}

    def set_rule(self, rule, allowed, resource_id):
        if not str(resource_id) in self.rules:
            self.rules[str(resource_id)] = {}

        self.rules[str(resource_id)][str(rule)] = allowed

    def toggle_admin_mode(self):
        if "ADMIN_MODE" not in self.rules:
            self.rules["ADMIN_MODE"] = True
        else:
            self.rules["ADMIN_MODE"] = bool(not self.rules["ADMIN_MODE"])

        return self.rules["ADMIN_MODE"]

    def is_allowed(self, rule, resource_id, default=False):
        if self.rules.get("ADMIN_MODE"):
            return False

        if not str(resource_id) in self.rules:
            return default

        if rule not in self.rules[str(resource_id)]:
            return default

        return str(self.rules[str(resource_id)][str(rule)]).strip().lower() in TRUTHY

    async def check_and_fail(self, rule, interaction):
        # Admin mode locks everyone else out, it must not lock out the admins managing it
        is_admin = any(
            getattr(role, "name", None) == ADMIN_ROLE
            for role in getattr(interaction.user, "roles", [])
        )
        if not (
            (is_admin and self.rules.get("ADMIN_MODE"))
            or self.is_allowed(rule, interaction.user.id, True)
        ):
            warn(
                self,
                f"The user {interaction.user.id} does not have permission to do that",
                interaction.guild,
            )
            from hifisuperstar.core.Server.Server import respond

            await respond(interaction, "Sorry, you are not permitted to do that.")
            return False

        return True
