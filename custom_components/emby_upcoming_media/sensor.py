"""
Home Assistant component to feed the Emby Mediarr card with
Emby Latest Media.

https://github.com/gcorgnet/sensor.emby_upcoming_media 2.0

"""
import logging
import json
import time
import re
import requests
import dateutil.parser
from datetime import date, datetime
from datetime import timedelta
import voluptuous as vol
from itertools import groupby
import homeassistant.helpers.config_validation as cv
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.components import sensor
from homeassistant.const import CONF_API_KEY, CONF_HOST, CONF_PORT, CONF_SSL
from homeassistant.helpers.entity import Entity

from .client import EmbyClient

__version__ = "0.0.1"

DOMAIN = "emby_upcoming_media 2.0"
DOMAIN_DATA = f"{DOMAIN}_data"
ATTRIBUTION = "Data is provided by Emby."

DICT_LIBRARY_TYPES = {"tvshows": "TV Shows", "movies": "Movies", "music": "Music"}

# Configuration
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


def setup_platform(hass, config, add_devices, discovery_info=None):

    # Create DATA dict
    hass.data[DOMAIN_DATA] = {}

    # Get "global" configuration.
    api_key = config.get(CONF_API_KEY)
    host = config.get(CONF_HOST)
    ssl = config.get(CONF_SSL)
    port = config.get(CONF_PORT)
    max_items = config.get(CONF_MAX)
    user_id = config.get(CONF_USER_ID)
    include = config.get(CONF_INCLUDE)
    show_episodes = config.get(CONF_EPISODES)

    # Configure the client.
    client = EmbyClient(host, api_key, ssl, port, max_items, user_id, show_episodes)
    hass.data[DOMAIN_DATA]["client"] = client

    categories = client.get_view_categories()
    
    categories = filter(lambda el: 'CollectionType' in el.keys() and el["CollectionType"] in DICT_LIBRARY_TYPES.keys(), categories) #just include supported library types (movie/tv)

    if include != []:
        categories = filter(lambda el: el["Name"] in include, categories)
            
    if config.get(CONF_GROUP_LIBRARIES) == True:
        l=[list(y) for x,y in groupby(sorted(list(categories),key=lambda x: (x['CollectionType'])),lambda x: (x['CollectionType']))]
        categories = [{k:(v if k!='Id' else list(set([x['Id'] for x in i]))) for k,v in i[0].items()} for i in l]

    mapped = map(
        lambda cat: EmbyUpcomingMediaSensor(
            hass, {**config, CATEGORY_NAME: cat["Name"], CATEGORY_ID: cat["Id"], CATEGORY_TYPE: DICT_LIBRARY_TYPES[cat["CollectionType"]]}
        ),
        categories,
    )

    add_devices(mapped, True)


SCAN_INTERVAL = timedelta(seconds=SCAN_INTERVAL_SECONDS)


class EmbyUpcomingMediaSensor(Entity):
    def __init__(self, hass, conf):
        self._client = hass.data[DOMAIN_DATA]["client"]
        self._state = None
        self.data = []
        self.use_backdrop = conf.get(CONF_USE_BACKDROP)
        self.category_name = (conf.get(CATEGORY_TYPE) if conf.get(CONF_GROUP_LIBRARIES) == True else conf.get(CATEGORY_NAME))
        self.category_id = conf.get(CATEGORY_ID)
        self.friendly_name = "Emby Latest Media " + self.category_name
        self.entity_id = sensor.ENTITY_ID_FORMAT.format(
            "emby_latest_"
            + re.sub(r"\_$", "", re.sub(r"\W+", "_", self.category_name)
            ).lower()
        )

    @property
    def name(self):
        return "Latest {0} on Emby".format(self.category_name)

    @property
    def state(self):
        return self._state

    def handle_tv_episodes(self):
        attributes = {}
        default = TV_DEFAULT
        card_json = [default]

        for show in self.data:
            card_item = {
                "id": show.get("Id"),
                "title": show.get("SeriesName"),
                "episode": show.get("Name", ""),
                "airdate": show.get("PremiereDate", datetime.now().isoformat()),
                "release": str(dateutil.parser.isoparse(show.get("PremiereDate", "")).year) if "PremiereDate" in show else "",
                "runtime": (timedelta(microseconds=show["RunTimeTicks"]/10).total_seconds()/60 if "RunTimeTicks" in show else ""),
                "number": f"S{show.get('ParentIndexNumber', 0):02d}E{show.get('IndexNumber', 0):02d}" if "ParentIndexNumber" in show and "IndexNumber" in show else f"Season {show.get('ParentIndexNumber', '')} Special",
                "poster": self._client.get_image_url(show.get("ParentBackdropItemId"), "Backdrop" if self.use_backdrop else "Primary") if "ParentBackdropItemId" in show else ""
            }
            card_json.append(card_item)

        attributes["data"] = card_json
        attributes["attribution"] = ATTRIBUTION
        return attributes

    def handle_tv_show(self):
        attributes = {}
        default = TV_ALTERNATE
        card_json = [default]

        for show in self.data:
            card_item = {
                "id": show.get("Id"),
                "title": show.get("Name"),
                "airdate": show.get("PremiereDate", datetime.now().isoformat()),
                "release": str(dateutil.parser.isoparse(show.get("PremiereDate", "")).year) if "PremiereDate" in show else "",
                "number": f"{show.get('ChildCount', 1)} season{'s' if show.get('ChildCount',1)>1 else ''}",
                "runtime": (timedelta(microseconds=show["RunTimeTicks"]/10).total_seconds()/60 if "RunTimeTicks" in show else ""),
                "genres": ", ".join(show.get("Genres", [])[:3]),
                "rating": f"\u2605 {show.get('CommunityRating', '')}" if "CommunityRating" in show else "",
                "poster": self._client.get_image_url(show.get("Id"), "Backdrop" if self.use_backdrop else "Primary")
            }
            card_json.append(card_item)

        attributes["data"] = card_json
        attributes["attribution"] = ATTRIBUTION
        return attributes

    def handle_movie(self):
        attributes = {}
        default = MOVIE_DEFAULT
        card_json = [default]

        for show in self.data:
            card_item = {
                "id": show.get("Id"),
                "title": show.get("Name"),
                "airdate": show.get("PremiereDate", datetime.now().isoformat()),
                "release": str(dateutil.parser.isoparse(show.get("PremiereDate", "")).year) if "PremiereDate" in show else "",
                "runtime": (timedelta(microseconds=show["RunTimeTicks"]/10).total_seconds()/60 if "RunTimeTicks" in show else ""),
                "genres": ", ".join(show.get("Genres", [])[:3]),
                "studio": show.get("Studios", [{}])[0].get("Name", "") if "Studios" in show else "",
                "rating": f"\u2605 {show.get('CommunityRating', '')}" if "CommunityRating" in show else "",
                "poster": self._client.get_image_url(show.get("Id"), "Backdrop" if self.use_backdrop else "Primary")
            }
            card_json.append(card_item)

        attributes["data"] = card_json
        attributes["attribution"] = ATTRIBUTION
        return attributes

    def handle_music(self):
        attributes = {}
        default = MUSIC_DEFAULT
        card_json = [default]

        for show in self.data:
            card_item = {
                "id": show.get("Id"),
                "title": show.get("Name"),
                "airdate": show.get("PremiereDate", datetime.now().isoformat()),
                "studio": ", ".join(show.get("Artists", [])[:3]) if "Artists" in show else "",
                "runtime": (timedelta(microseconds=show["RunTimeTicks"]/10).total_seconds()/60 if "RunTimeTicks" in show else ""),
                "genres": ", ".join(show.get("Genres", [])[:3]),
                "release": str(show.get("ProductionYear", "")),
                "number": f"S{show.get('ParentIndexNumber', 0):02d}E{show.get('IndexNumber', 0):02d}" if "ParentIndexNumber" in show and "IndexNumber" in show else show.get("ProductionYear", ""),
                "rating": f"\u2605 {show.get('CommunityRating', '')}" if "CommunityRating" in show else "",
                "poster": self._client.get_image_url(show.get("Id"), "Primary")
            }
            card_json.append(card_item)

        attributes["data"] = card_json
        attributes["attribution"] = ATTRIBUTION
        return attributes

    @property
    def extra_state_attributes(self):
        if not self.data:
            return {}

        first_type = self.data[0].get("Type", "")
        if first_type == "Episode":
            return self.handle_tv_episodes()
        elif first_type == "Series":
            return self.handle_tv_show()
        elif first_type == "Movie":
            return self.handle_movie()
        elif first_type in ["MusicAlbum", "Audio"]:
            return self.handle_music()
        else:
            attributes = {"data": [], "attribution": ATTRIBUTION}
            return attributes

    def update(self):
        if isinstance(self.category_id, str): 
            data = self._client.get_data(self.category_id)
        else:
            data = []
            for element in self.category_id:
                data.extend(self._client.get_data(element))
            data.sort(key=lambda item: item.get('DateCreated', ""), reverse=True)

        if data is not None:
            self._state = "Online"
            self.data = data
        else:
            self._state = "error"
            _LOGGER.error("Failed to fetch Emby data for category %s", self.category_name)

