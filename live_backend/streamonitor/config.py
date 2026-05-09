import json
import os
import sys
import time

from streamonitor.bot import Bot
# Import all sites to register them with Bot.loaded_sites
import streamonitor.sites
import streamonitor.log as log

# 2026-05-09: when StreaMonitor runs vendored inside the Harvestr universal
# harvester, the universal harvester's own `config.json` (a dict with
# `performers`, `enabled_sites`, etc.) sits in the same cwd that StreaMonitor
# would use for its `config.json` (a LIST of streamer dicts). They collide on
# the same filename and StreaMonitor ends up with 0 streamers loaded.
# The host (universal/live_recording.py) sets STRMNTR_CONFIG_PATH to a
# distinct absolute path so the two configs never share a filename.
config_loc = os.environ.get("STRMNTR_CONFIG_PATH", "config.json")
logger = log.Logger("config")


def load_config():
    try:
        with open(config_loc, "r+") as f:
            return json.load(f)
    except FileNotFoundError:
        with open(config_loc, "w+") as f:
            json.dump([], f, indent=4)
            return []
    except Exception as e:
        logger.error(f"Failed to load config: {e}", exc_info=True)
        sys.exit(1)


def save_config(config):
    try:
        with open(config_loc, "w+") as f:
            json.dump(config, f, indent=4)

        return True
    except Exception as e:
        logger.error(f"Failed to save config: {e}", exc_info=True)
        sys.exit(1)


def loadStreamers():
    streamers = []
    for streamer in load_config():
        room_id = streamer.get('room_id')
        username = streamer["username"]
        site = streamer["site"]
        if room_id:
            streamer_bot = Bot.str2site(site)(username, room_id=room_id)
        else:
            streamer_bot = Bot.str2site(site)(username)
        # Restore gender and country from config
        gender_val = streamer.get('gender')
        if gender_val is not None:
            try:
                from streamonitor.enums import Gender
                streamer_bot.gender = Gender(gender_val)
            except (ValueError, KeyError):
                pass
        country = streamer.get('country')
        if country:
            streamer_bot.country = country
        streamers.append(streamer_bot)
        streamer_bot.start()
        if streamer["running"]:
            streamer_bot.restart()
            time.sleep(0.1)
    return streamers
