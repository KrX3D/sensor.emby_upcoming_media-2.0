# 🎬 Emby Upcoming Media 2.0

[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/hacs/integration)

**Home Assistant component to feed the [emby-mediarr-card](https://github.com/Stefan765/emby-mediarr-card) with the latest releases from your Emby server.**  

This component **does not require** the default Emby integration and runs independently.

---

## ❤️ Support This Project
If you find this project useful, please consider supporting it!  
Your contributions help maintain and improve the project.

---

## ✨ Features
- Fetches the latest movies and TV shows from Emby  
- Option to group all libraries into **one movie sensor** and **one TV show sensor**  
- Configurable number of items per sensor  
- Supports backdrop images for cards  
- **Overview Function:**  
  - Shows the movie description for each entry from your Emby server  
- Works seamlessly with the [emby-mediarr-card](https://github.com/Stefan765/emby-mediarr-card)

---

## ⚙️ Installation

### HACS / Manual Installation
1. Copy the component files into: /custom_components/emby_upcoming_media/
2. 2. Install the **emby-mediarr-card** for Lovelace separately  
3. Add the configuration to your `configuration.yaml`  
4. Restart Home Assistant

---

## 🧩 Configuration Options

| Key              | Default   | Required | Description |
|-----------------|-----------|----------|-------------|
| api_key          |           | yes      | Your Emby API key |
| user_id          |           | yes      | User ID to impersonate (not username) |
| host             | localhost | no       | Emby server host |
| port             | 8096      | no       | Emby server port |
| ssl              | false     | no       | Use SSL (https) |
| max              | 5         | no       | Max number of items per sensor |
| use_backdrop     | false     | no       | Use backdrop images instead of posters |
| include          |           | no       | Names of libraries to include; creates separate sensors per library if not set |
| group_libraries  | false     | no       | Group movies and TV into two sensors (`emby_movies_entity` / `emby_series_entity`) |
| episodes         | true      | no       | Show episodes (TV) or songs (Music); false shows seasons/albums |

---

### Example `configuration.yaml` (per library)

```yaml
sensor:
- platform: emby_upcoming_media
 api_key: YOUR_EMBY_API_KEY
 user_id: YOUR_EMBY_USER_ID
 host: xxxxx
 port: 8096
 ssl: true
 max: 5
 use_backdrop: true
 group_libraries: false
 episodes: false
 include:
   - Movies
   - Kids Movies
   - TV Shows
   - Music

Example configuration.yaml (grouped sensors)

sensor:
  - platform: emby_upcoming_media
    api_key: YOUR_EMBY_API_KEY
    user_id: YOUR_EMBY_USER_ID
    host: xxxxx
    port: 8096
    ssl: true
    max: 5
    use_backdrop: true
    group_libraries: true

This will create emby_movies_entity and emby_series_entity sensors for use in Lovelace.

- type: custom:emby-mediarr-card
  movies_entity: sensor.emby_movies_entity
  series_entity: sensor.emby_series_entity
  title: Latest Emby Releases


