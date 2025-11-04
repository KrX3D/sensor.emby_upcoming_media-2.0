"""
Home Assistant component to feed the Emby Media card with
Emby Latest Media.

https://github.com/Stefan765/sensor.emby_upcoming_media-2.0
"""
import logging
import json
import re
import requests
import dateutil.parser
from datetime import datetime, timedelta
import voluptuous as vol
from itertools import groupby
import homeassistant.helpers.config_validation as cv
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.components import sensor
from homeassistant.const import CONF_API_KEY, CONF_HOST, CONF_PORT, CONF_SSL
from homeassistant.helpers.entity import Entity

__version__ = "0.0.1"

DOMAIN = "emby_upcoming_media"
DOMAIN_DATA = f"{DOMAIN}_data"
ATTRIBUTION = "Data is provided by Emby."

DICT_LIBRARY_TYPES = {"tvshows": "TV Shows", "movies": "Movies", "music": "Music"}

# Configuration keys
CONF_SENSOR = "sensor"
CONF_ENABLED = "enabled"
CONF_NAME = "name"
CONF_INCLUDE = "include"
CONF_MAX = "max"
CONF_USER_ID = "user_id"
CONF_USE_BACKDROP = "use_backdrop"
CONF_GROUP_LIBRARIES = "group_libraries"
CONF_EPISODES = "episodes"

CATEGORY_NAME = "CategoryName"
CATEGORY_ID = "CategoryId"
CATEGORY_TYPE = "CollectionType"

SCAN_INTERVAL_SECONDS = 3600  # Scan once per hour

# Default card templates
TV_DEFAULT = {"title_default": "$title", "line1_default": "$release", "line2_default": "$number", "line3_default": "$episode", "line4_default": "Runtime: $runtime", "icon": "mdi:arrow-down-bold"}
TV_ALTERNATE = {"title_default": "$title", "line1_default": "$release • $number", "line2_default": "Average Runtime: $runtime", "line3_default": "$genres", "line4_default": "$rating", "icon": "mdi:arrow-down-bold"}
MOVIE_DEFAULT = {"title_default": "$title", "line1_default": "$release", "line2_default": "Runtime: $runtime", "line3_default": "$genres", "line4_default": "$rating", "icon": "mdi:arrow-down-bold"}
MUSIC_DEFAULT = {"title_default": "$title", "line1_default": "$studio • $release", "line2_default": "Runtime: $runtime", "line3_default": "$genres", "line4_default": "", "icon": "mdi:arrow-down-bold"}
OTHER_DEFAULT = {"title_default": "$title", "line1_default": "$release", "line2_default": "Runtime: $runtime", "line3_default": "$genres", "line4_default": "$studio", "icon": "mdi:arrow-down-bold"}

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_API_KEY): cv.string,
        vol.Optional(CONF_USER_ID): cv.string,
        vol.Optional(CONF_HOST, default="localhost"): cv.string,
        vol.Optional(CONF_PORT, default=8096): cv.port,
        vol.Optional(CONF_SSL, default=False): cv.boolean,
        vol.Optional(CONF_INCLUDE, default=[]): vol.All(cv.ensure_list),
        vol.Optional(CONF_MAX, default=5): cv.Number,
        vol.Optional(CONF_USE_BACKDROP, default=False): cv.boolean,
        vol.Optional(CONF_GROUP_LIBRARIES, default=False): cv.boolean,
        vol.Optional(CONF_EPISODES, default=True): cv.boolean
    }
)

# -----------------------------
# Emby Client
# -----------------------------
class EmbyClient:
    def __init__(self, host, api_key, ssl=False, port=8096, max_items=5, user_id=None, show_episodes=True):
        self.host = host
        self.api_key = api_key
        self.ssl = ssl
        self.port = port
        self.max_items = max_items
        self.user_id = user_id
        self.show_episodes = show_episodes
        self.base_url = f"{'https' if ssl else 'http'}://{host}:{port}/emby"

    def get_data(self, category_id):
        """Fetch media items from a library with detailed fields including Overview."""
        try:
            url = (
                f"{self.base_url}/Items"
                f"?ParentId={category_id}"
                f"&IncludeItemTypes=Movie,Series,Episode,MusicAlbum"
                f"&Fields=Overview,Genres,Studios,CommunityRating,RunTimeTicks,Artists"
                f"&SortBy=DateCreated"
                f"&SortOrder=Descending"
                f"&Limit={self.max_items}"
            )
            headers = {"X-Emby-Token": self.api_key}
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data.get("Items", [])
        except Exception as e:
            _LOGGER.error("Fehler beim Abrufen von Daten aus Emby: %s", e)
            return []

# -----------------------------
# Setup Platform
# -----------------------------
def setup_platform(hass, config, add_devices, discovery_info=None):

    # Create DATA dict
    hass.data[DOMAIN_DATA] = {}

    # Get config
    api_key = config.get(CONF_API_KEY)
    host = config.get(CONF_HOST)
    ssl = config.get(CONF_SSL)
    port = config.get(CONF_PORT)
    max_items = config.get(CONF_MAX)
    user_id = config.get(CONF_USER_ID)
    include = config.get(CONF_INCLUDE)
    show_episodes = config.get(CONF_EPISODES)

    # Configure client
    client = EmbyClient(host, api_key, ssl, port, max_items, user_id, show_episodes)
    hass.data[DOMAIN_DATA]["client"] = client

    categories = client.get_data("")  # initial call may need adjustment
    categories = filter(lambda el: 'CollectionType' in el.keys() and el["CollectionType"] in DICT_LIBRARY_TYPES.keys(), categories)

    if include:
        categories = filter(lambda el: el["Name"] in include, categories)

    if config.get(CONF_GROUP_LIBRARIES):
        l = [list(y) for x, y in groupby(sorted(list(categories), key=lambda x: x['CollectionType']), lambda x: x['CollectionType'])]
        categories = [{k: (v if k != 'Id' else list(set([x['Id'] for x in i]))) for k, v in i[0].items()} for i in l]

    mapped = map(
        lambda cat: EmbyUpcomingMediaSensor(
            hass, {**config, CATEGORY_NAME: cat["Name"], CATEGORY_ID: cat["Id"], CATEGORY_TYPE: DICT_LIBRARY_TYPES[cat["CollectionType"]]}
        ),
        categories,
    )

    add_devices(mapped, True)

SCAN_INTERVAL = timedelta(seconds=SCAN_INTERVAL_SECONDS)

# -----------------------------
# Sensor Entity
# -----------------------------
class EmbyUpcomingMediaSensor(Entity):
    def __init__(self, hass, conf):
        self._client = hass.data[DOMAIN_DATA]["client"]
        self._state = None
        self.data = []
        self.use_backdrop = conf.get(CONF_USE_BACKDROP)
        self.category_name = conf.get(CATEGORY_TYPE) if conf.get(CONF_GROUP_LIBRARIES) else conf.get(CATEGORY_NAME)
        self.category_id = conf.get(CATEGORY_ID)
        self.friendly_name = "Emby Latest Media " + self.category_name
        self.entity_id = sensor.ENTITY_ID_FORMAT.format(
            "emby_latest_" + re.sub(r"\W+", "_", self.category_name).lower()
        )

    @property
    def name(self):
        return f"Latest {self.category_name} on Emby"

    @property
    def state(self):
        return self._state

    @property
    def extra_state_attributes(self):
        # Logic for TV shows, movies, music, etc.
        if not self.data:
            return {}
        type_map = {
            "Episode": self.handle_tv_episodes,
            "Series": self.handle_tv_show,
            "Movie": self.handle_movie,
            "MusicAlbum": self.handle_music,
            "Audio": self.handle_music,
        }
        handler = type_map.get(self.data[0].get("Type"), self.handle_other)
        return handler()

    # ----- Handlers for different media types -----
    def handle_tv_episodes(self):
        attributes = {}
        card_json = [TV_DEFAULT]
        for show in self.data:
            card_item = {}
            card_item["title"] = show.get("SeriesName", "")
            card_item["episode"] = show.get("Name", "")
            card_item["airdate"] = show.get("PremiereDate", datetime.now().isoformat())
            card_item["release"] = str(dateutil.parser.isoparse(show.get("PremiereDate", "")).year) if "PremiereDate" in show else ""
            card_item["runtime"] = timedelta(microseconds=show.get("RunTimeTicks", 0) / 10).total_seconds() / 60 if "RunTimeTicks" in show else ""
            card_item["number"] = f"S{show['ParentIndexNumber']:02d}E{show['IndexNumber']:02d}" if "ParentIndexNumber" in show and "IndexNumber" in show else f"Season {show.get('ParentIndexNumber', '')} Special"
            if "ParentBackdropItemId" in show:
                card_item["poster"] = self._client.get_image_url(show["ParentBackdropItemId"], "Backdrop" if self.use_backdrop else "Primary")
            overview_clean = re.sub(r'<[^>]+>', '', show.get("Overview", "")).strip()
            card_item["summary"] = overview_clean if overview_clean else "Keine Beschreibung verfügbar."
            card_item["id"] = show.get("Id", "")
            card_json.append(card_item)
        attributes["data"] = json.dumps(card_json)
        attributes["attribution"] = ATTRIBUTION
        return attributes

    def handle_tv_show(self):
        attributes = {}
        card_json = [TV_ALTERNATE]
        for show in self.data:
            card_item = {}
            card_item["title"] = show["Name"]
            card_item["airdate"] = show.get("PremiereDate", datetime.now().isoformat())
            card_item["release"] = str(dateutil.parser.isoparse(show.get("PremiereDate", "")).year) if "PremiereDate" in show else ""
            card_item["number"] = f"{show.get('ChildCount', 1)} season(s)"
            card_item["runtime"] = timedelta(microseconds=show.get("RunTimeTicks", 0) / 10).total_seconds() / 60 if "RunTimeTicks" in show else ""
            card_item["genres"] = ", ".join(show.get("Genres", [])[:3])
            card_item["rating"] = f"\u2605 {show.get('CommunityRating', ''):.1f}" if "CommunityRating" in show else ""
            overview_clean = re.sub(r'<[^>]+>', '', show.get("Overview", "")).strip()
            card_item["summary"] = overview_clean if overview_clean else "Keine Beschreibung verfügbar."
            card_item["poster"] = self._client.get_image_url(show["Id"], "Backdrop" if self.use_backdrop else "Primary")
            card_item["id"] = show.get("Id", "")
            card_json.append(card_item)
        attributes["data"] = json.dumps(card_json)
        attributes["attribution"] = ATTRIBUTION
        return attributes

    def handle_movie(self):
        attributes = {}
        card_json = [MOVIE_DEFAULT]
        for show in self.data:
            card_item = {}
            card_item["title"] = show.get("Name", "")
            card_item["release"] = str(dateutil.parser.isoparse(show.get("PremiereDate", "")).year) if "PremiereDate" in show else ""
            card_item["runtime"] = timedelta(microseconds=show.get("RunTimeTicks", 0) / 10).total_seconds() / 60 if "RunTimeTicks" in show else ""
            card_item["genres"] = ", ".join(show.get("Genres", [])[:3])
            card_item["rating"] = f"\u2605 {show.get('CommunityRating', ''):.1f}" if "CommunityRating" in show else ""
            overview_clean = re.sub(r'<[^>]+>', '', show.get("Overview", "")).strip()
            card_item["summary"] = overview_clean if overview_clean else "Keine Beschreibung verfügbar."
            card_item["poster"] = self._client.get_image_url(show["Id"], "Backdrop" if self.use_backdrop else "Primary")
            card_item["id"] = show.get("Id", "")
            card_json.append(card_item)
        attributes["data"] = json.dumps(card_json)
        attributes["attribution"] = ATTRIBUTION
        return attributes

    def handle_music(self):
        attributes = {}
        card_json = [MUSIC_DEFAULT]
        # similar logic as movie/tv
        return attributes

    def handle_other(self):
        attributes = {}
        card_json = [OTHER_DEFAULT]
        return attributes

    def update(self):
        """Fetch latest data from Emby for the sensor."""
        self.data = self._client.get_data(self.category_id)
        self._state = len(self.data)
