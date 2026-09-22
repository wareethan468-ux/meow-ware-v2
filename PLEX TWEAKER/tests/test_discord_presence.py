from src.utils.discord_presence import DiscordPresence, DEFAULT_CLIENT_ID


def test_discord_presence_empty_client_id_noops():
    presence = DiscordPresence("")
    presence.start()
    assert presence._thread is None
    presence.stop()


def test_discord_presence_default_client_id():
    presence = DiscordPresence()
    assert presence.client_id == DEFAULT_CLIENT_ID
    assert presence.client_id == "1543317341448704050"


def test_discord_presence_custom_client_id():
    presence = DiscordPresence("987654321")
    assert presence.client_id == "987654321"
    presence.stop()

