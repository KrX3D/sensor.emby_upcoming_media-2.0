"""Client."""
import datetime
import requests
import logging

_LOGGER = logging.getLogger(__name__)


class EmbyClient:
    """Client class"""

    def __init__(self, host, api_key, ssl, port, max_items, user_id, show_episodes):
        """Init."""
        self.data = {}
        self.host = host
        self.ssl = "s" if ssl else ""
        self.port = port
        self.api_key = api_key
        self.user_id = user_id
        self.max_items = max_items
        self.show_episodes = "&GroupItems=False" if show_episodes else ""

    def get_view_categories(self):
        """This will pull the list of all View Categories on Emby"""
        try:
            url = "http{0}://{1}:{2}/Users/{3}/Views?api_key={4}".format(
                self.ssl, self.host, self.port, self.user_id, self.api_key
            )
            _LOGGER.info("Making API call on URL %s", url)
            api = requests.get(url, timeout=10)
        except OSError:
            _LOGGER.warning("Host %s is not available", self.host)
            self._state = "%s cannot be reached" % self.host
            return

        if api.status_code == 200:
            self.data["ViewCategories"] = api.json()["Items"]

        else:
            _LOGGER.info("Could not reach url %s", url)
            self._state = "%s cannot be reached" % self.host

        return self.data["ViewCategories"]

    def get_data(self, category_id):
        """
        Ruft alle Items einer Kategorie ab und liefert eine Liste von Dictionaries zurück.
        Unterstützt Filme, Serien, Episoden und Musikalben.
        """
        fields = [
            "Overview",
            "Genres",
            "Studios",
            "Artists",
            "CommunityRating",
            "RunTimeTicks",
            "ParentIndexNumber",
            "IndexNumber",
            "ProductionYear",
        ]
    
        include_types = ["Movie", "Series", "Episode", "MusicAlbum", "Audio"]
    
        url = (
            f"{self.base_url}/Items?"
            f"ParentId={category_id}&"
            f"IncludeItemTypes={','.join(include_types)}&"
            f"Fields={','.join(fields)}"
        )
    
        try:
            r = requests.get(url, headers={"X-Emby-Token": self.api_key}, timeout=10)
            r.raise_for_status()
            items = r.json().get("Items", [])
            items.sort(key=lambda item: item.get("DateCreated", ""), reverse=True)
            return items
    
        except requests.exceptions.RequestException as e:
            _LOGGER.error("Fehler beim Abrufen der Emby-Daten: %s", e)
            return []
    

    def get_image_url(self, itemId, imageType):
        url = "http{0}://{1}:{2}/Items/{3}/Images/{4}?maxHeight=360&maxWidth=640&quality=90".format(
            self.ssl, self.host, self.port, itemId, imageType
        )
        return url
            
