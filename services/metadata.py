import re
import json
import math
from urllib.parse import urlparse, parse_qs
import requests
from bs4 import BeautifulSoup


def get_provider(url: str) -> str:
    """Erkennt den Provider anhand der URL."""
    try:
        hostname = urlparse(url).hostname or ''
        hostname = hostname.lower().replace('www.', '')

        mapping = {
            'youtube.com': 'YouTube',
            'youtu.be': 'YouTube',
            'vimeo.com': 'Vimeo',
            'dailymotion.com': 'Dailymotion',
            'twitch.tv': 'Twitch',
            'netflix.com': 'Netflix',
            'arte.tv': 'Arte',
            'zdf.de': 'ZDF',
            'ard.de': 'ARD',
            'mediathek.ard.de': 'ARD Mediathek',
            'ardmediathek.de': 'ARD Mediathek',
            'funk.net': 'Funk',
            'ted.com': 'TED',
            'rumble.com': 'Rumble',
            'odysee.com': 'Odysee',
            'bitchute.com': 'BitChute',
            'dropbox.com': 'Dropbox',
            'dl.dropboxusercontent.com': 'Dropbox',
        }

        for domain, name in mapping.items():
            if hostname == domain or hostname.endswith('.' + domain):
                return name

        # Fallback: Domain-Name ohne TLD
        parts = hostname.split('.')
        if len(parts) >= 2:
            return parts[-2].capitalize()
        return hostname.capitalize()
    except Exception:
        return 'Unbekannt'


def get_youtube_video_id(url: str) -> str | None:
    """Extrahiert die YouTube Video-ID."""
    parsed = urlparse(url)
    hostname = parsed.hostname or ''
    if 'youtu.be' in hostname:
        return parsed.path.lstrip('/')
    if 'youtube.com' in hostname:
        qs = parse_qs(parsed.query)
        if 'v' in qs:
            return qs['v'][0]
        # Shorts: /shorts/VIDEO_ID
        match = re.search(r'/shorts/([a-zA-Z0-9_-]+)', parsed.path)
        if match:
            return match.group(1)
    return None


def _parse_iso8601_duration(iso: str) -> int | None:
    """Wandelt ISO-8601-Dauer (PT4M13S) in Minuten um."""
    try:
        match = re.match(
            r'P(?:(\d+)D)?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', iso
        )
        if not match:
            return None
        days = int(match.group(1) or 0)
        hours = int(match.group(2) or 0)
        minutes = int(match.group(3) or 0)
        seconds = int(match.group(4) or 0)
        total_sec = days * 86400 + hours * 3600 + minutes * 60 + seconds
        return max(1, math.ceil(total_sec / 60))
    except Exception:
        return None


def get_youtube_data(url: str) -> dict:
    """Holt Titel, Thumbnail und Länge von YouTube via Seitenanalyse."""
    result = {'title': '', 'thumbnail': '', 'duration_min': None}
    try:
        vid_id = get_youtube_video_id(url)
        if vid_id:
            result['thumbnail'] = f'https://img.youtube.com/vi/{vid_id}/hqdefault.jpg'

        headers = {
            'User-Agent': (
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            ),
            'Accept-Language': 'de-DE,de;q=0.9',
        }
        resp = requests.get(url, headers=headers, timeout=8)
        html = resp.text

        # Titel aus og:title
        soup = BeautifulSoup(html, 'html.parser')
        og_title = soup.find('meta', property='og:title')
        if og_title:
            result['title'] = og_title.get('content', '')
        elif soup.title:
            result['title'] = (soup.title.string or '').replace(' - YouTube', '').strip()

        # Länge: "lengthSeconds":"245" im eingebetteten JSON
        m = re.search(r'"lengthSeconds"\s*:\s*"(\d+)"', html)
        if m:
            secs = int(m.group(1))
            result['duration_min'] = max(1, math.ceil(secs / 60))
        else:
            # Fallback: JSON-LD mit ISO 8601 Dauer
            m2 = re.search(r'"duration"\s*:\s*"(PT[^"]+)"', html)
            if m2:
                result['duration_min'] = _parse_iso8601_duration(m2.group(1))

    except Exception:
        pass
    return result


def get_vimeo_data(url: str) -> dict:
    """Holt Daten via Vimeo oEmbed (inkl. Dauer)."""
    result = {'title': '', 'thumbnail': '', 'duration_min': None}
    try:
        resp = requests.get(
            'https://vimeo.com/api/oembed.json',
            params={'url': url},
            timeout=6
        )
        if resp.ok:
            data = resp.json()
            result['thumbnail'] = data.get('thumbnail_url', '')
            result['title'] = data.get('title', '')
            duration_sec = data.get('duration')  # Sekunden
            if duration_sec:
                result['duration_min'] = max(1, math.ceil(int(duration_sec) / 60))
    except Exception:
        pass
    return result


def get_og_data(url: str) -> dict:
    """Liest Open-Graph-Metadaten aus einer URL."""
    result = {'title': '', 'image': ''}
    try:
        headers = {
            'User-Agent': (
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            )
        }
        resp = requests.get(url, headers=headers, timeout=6)
        soup = BeautifulSoup(resp.text, 'html.parser')

        og_title = soup.find('meta', property='og:title')
        if og_title:
            result['title'] = og_title.get('content', '')
        elif soup.title:
            result['title'] = soup.title.string or ''

        og_image = soup.find('meta', property='og:image')
        if og_image:
            result['image'] = og_image.get('content', '')
    except Exception:
        pass
    return result


def get_microlink_thumbnail(url: str) -> str | None:
    """Fallback: Microlink API für Screenshot/Thumbnail."""
    try:
        resp = requests.get(
            'https://api.microlink.io',
            params={'url': url, 'screenshot': 'true'},
            timeout=8
        )
        if resp.ok:
            data = resp.json()
            img = data.get('data', {}).get('image', {})
            if img and img.get('url'):
                return img['url']
            ss = data.get('data', {}).get('screenshot', {})
            if ss and ss.get('url'):
                return ss['url']
    except Exception:
        pass
    return None


def get_dropbox_data(url: str) -> dict:
    """Dropbox: Thumbnail via OG-Tags, URL normalisieren für direktes Abspielen."""
    result = {'title': '', 'thumbnail': '', 'duration_min': None}
    try:
        og = get_og_data(url)
        result['title'] = og.get('title', '').replace(' - Dropbox', '').strip()
        result['thumbnail'] = og.get('image', '')
    except Exception:
        pass
    return result


def analyze_url(url: str) -> dict:
    """Hauptfunktion: Analysiert eine URL und gibt alle Metadaten zurück."""
    provider = get_provider(url)
    thumbnail = ''
    title = ''
    duration_min = None

    try:
        hostname = urlparse(url).hostname or ''
        hostname = hostname.lower().replace('www.', '')

        if 'youtube.com' in hostname or 'youtu.be' in hostname:
            data = get_youtube_data(url)
            thumbnail = data['thumbnail']
            title = data['title']
            duration_min = data['duration_min']

        elif 'vimeo.com' in hostname:
            data = get_vimeo_data(url)
            thumbnail = data['thumbnail']
            title = data['title']
            duration_min = data['duration_min']

        elif 'dropbox.com' in hostname or 'dropboxusercontent.com' in hostname:
            data = get_dropbox_data(url)
            title = data['title']
            thumbnail = data['thumbnail']

        else:
            og = get_og_data(url)
            title = og.get('title', '')
            thumbnail = og.get('image', '')
            if not thumbnail:
                thumbnail = get_microlink_thumbnail(url) or ''

    except Exception:
        pass

    return {
        'provider': provider,
        'thumbnail_url': thumbnail,
        'titel': title.strip(),
        'laenge_min': duration_min,  # None wenn unbekannt
    }
