"""Tango Live recorder.

Tango.me is a live-streaming platform with a heavily JS-rendered SPA and
auth-token-protected master.m3u8 URLs. As of May 2026 (yt-dlp issue #11433),
there's no clean public API for resolving username → live status → m3u8.
The auth flow involves a `tokenData` fetch every 10s + cookies (`tt`, `ttu`,
`tte`) that gate the playlist URL.

This bot supports TWO modes:

  1. **Manual m3u8 mode (RECOMMENDED, RELIABLE)** — pass a master.m3u8 URL
     in the `room_id` field. The bot probes that URL to detect when it
     returns 200 (= broadcaster live + URL still valid) vs 4xx (offline
     or token expired). When live, ffmpeg records via the standard Bot
     pipeline.

     How to extract the URL:
       a. Open https://www.tango.me/ in a browser, find a streamer in
          the **Following** tab (their tokens are static — Following-tab
          streams DO NOT have token-refresh, so the m3u8 URL stays valid
          for the duration of the live show).
       b. Open DevTools → Network tab → click the streamer
       c. Filter by "m3u8" → copy the master.m3u8?token=<...> URL
       d. Add the bot via the UI with username = display name and
          room_id = the m3u8 URL.

  2. **Username mode (EXPERIMENTAL, not yet wired up)** — pass only the
     username. The bot would need to use a headless browser to render
     the profile page, detect live status, and intercept the m3u8 URL
     from network requests every status check. NOT IMPLEMENTED here
     because it'd consume too many resources at scale and the auth
     flow rotates frequently.

References:
  https://github.com/yt-dlp/yt-dlp/issues/11433 (open issue, no upstream
  solution as of May 2026). Two community recorder repos referenced in
  the issue (MrR00tsuz/tango.me-live-stream-find,
  MrR00tsuz/tango.me-live-stream-recorder) both went 404, suggesting
  active enforcement against tooling. This bot stays minimal and
  user-driven to avoid that vector.
"""
from __future__ import annotations

import re
from typing import Optional, Dict, Any, Tuple, List
import requests

from streamonitor.bot import RoomIdBot
from streamonitor.enums import Status


class Tango(RoomIdBot):
    site: str = 'Tango'
    siteslug: str = 'TGO'

    # Tango.me's master.m3u8 URLs look like:
    #   https://<region>.cdn.tango.me/<...>/master.m3u8?token=<long>
    # The token is part of the URL itself; no extra cookies needed for
    # Following-tab streams.
    _MASTER_URL_RE = re.compile(
        r'https?://[^\s"\']+master\.m3u8(?:\?[^\s"\']*)?$', re.IGNORECASE,
    )

    def __init__(self, username: str, room_id: Optional[str] = None) -> None:
        # In Tango's bot, room_id IS the master.m3u8 URL (override the
        # numeric-username heuristic the parent uses for SC/F4F).
        if room_id is None:
            # Allow username field to carry the URL too, for manual entry
            if username and "master.m3u8" in username:
                room_id = username
        super().__init__(username, room_id=room_id)
        self.url = self.getWebsiteURL()

    def get_site_color(self) -> Tuple[str, List[str]]:
        return ("light_red", [])

    def getWebsiteURL(self) -> str:
        """Public profile URL (used by the UI's 'open profile' button)."""
        return f"https://www.tango.me/{self.username}"

    # RoomIdBot hooks — Tango doesn't have an open API to resolve names,
    # so we don't auto-discover. The user supplies the m3u8 URL directly.
    def getRoomIdFromUsername(self, username: str) -> Optional[str]:
        return None

    def getUsernameFromRoomId(self, room_id: str) -> Optional[str]:
        return None

    def getVideoUrl(self) -> Optional[str]:
        """Return the master.m3u8 URL stored in room_id."""
        if self.room_id and self._MASTER_URL_RE.match(self.room_id):
            return self.room_id
        return None

    def getStatus(self) -> Status:
        """Probe the m3u8 URL: 200/206 → live, 4xx → offline/expired.

        Note: CFSessionManager (this project's HTTP wrapper) only exposes
        `get`/`post` — no HEAD. We use a Range GET (`bytes=0-0`) which
        downloads at most one byte and works against every signed-URL
        CDN we've encountered, including Tango's.
        """
        if not self.room_id or not self._MASTER_URL_RE.match(self.room_id):
            self.logger.warning(
                "Tango bot has no master.m3u8 URL configured. "
                "Edit the model and set 'room_id' to a master.m3u8?token=... "
                "URL extracted from your browser's Network tab while "
                "viewing the streamer in Tango's 'Following' tab."
            )
            return Status.NOTEXIST

        url = self.room_id
        try:
            r = self.session.get(
                url,
                headers={**self.headers, "Range": "bytes=0-0"},
                timeout=15, allow_redirects=True, bucket='status',
            )
            status = r.status_code

            if status in (200, 206):
                return Status.PUBLIC
            if status == 404:
                return Status.OFFLINE
            if status in (401, 403):
                # Token expired or revoked — broadcaster effectively
                # offline from our perspective; user must re-extract.
                self.logger.info(
                    "Tango master.m3u8 returned %s — token expired or "
                    "stream ended. Re-extract a fresh URL from the "
                    "browser's Network tab.",
                    status,
                )
                return Status.OFFLINE
            if status == 410:
                # Gone — stream ended for good
                return Status.OFFLINE
            self.logger.warning(f"Tango status probe got HTTP {status}")
            return Status.UNKNOWN

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Network error checking status: {e}")
            return Status.ERROR
        except Exception as e:
            self.logger.error(f"Unexpected error [{type(e).__name__}]: {e!r}")
            return Status.ERROR

    def isMobile(self) -> bool:
        return False
