import re
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
    if 'youtu.be' in parsed.hostname:
        return parsed.path.lstrip('/')
    if 'youtube.com' in parsed.hostname:
        qs = parse_qs(parsed.query)
        if 'v' in qs:
            return qs['v'][0]
        # Shorts: /shorts/VIDEO_ID
        match = re.search(r'/shorts/([a-zA-Z0-9_-]+)', parsed.path)
        if match:
            return match.group(1)
    return None


def get_vimeo_thumbnail(url: str) -> str | None:
    """Holt das Thumbnail via Vimeo oEmbed."""
    try:
        resp = requests.get(
            'https://vimeo.com/api/oembed.json',
            params={'url': url},
            timeout=5
        )
        if resp.ok:
            data = resp.json()
            return data.get('thumbnail_url')
    except Exception:
        pass
    return None


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

        # og:title
        og_title = soup.find('meta', property='og:title')
        if og_title:
            result['title'] = og_title.get('content', '')
        elif soup.title:
            result['title'] = soup.title.string or ''

        # og:image
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
            # Versuche zuerst og:image
            img = data.get('data', {}).get('image', {})
            if img and img.get('url'):
                return img['url']
            # Dann Screenshot
            ss = data.get('data', {}).get('screenshot', {})
            if ss and ss.get('url'):
                return ss['url']
    except Exception:
        pass
    return None


def analyze_url(url: str) -> dict:
    """Hauptfunktion: Analysiert eine URL und gibt alle Metadaten zurück."""
    provider = get_provider(url)
    thumbnail = None
    title = ''

    try:
        hostname = urlparse(url).hostname or ''
        hostname = hostname.lower().replace('www.', '')

        if 'youtube.com' in hostname or 'youtu.be' in hostname:
            vid_id = get_youtube_video_id(url)
            if vid_id:
                thumbnail = f'https://img.youtube.com/vi/{vid_id}/hqdefault.jpg'
            og = get_og_data(url)
            title = og.get('title', '')

        elif 'vimeo.com' in hostname:
            thumbnail = get_vimeo_thumbnail(url)
            if not thumbnail:
                og = get_og_data(url)
                thumbnail = og.get('image', '')
                title = og.get('title', '')
            else:
                og = get_og_data(url)
                title = og.get('title', '')

        else:
            og = get_og_data(url)
            title = og.get('title', '')
            thumbnail = og.get('image', '')
            if not thumbnail:
                thumbnail = get_microlink_thumbnail(url)

    except Exception:
        pass

    return {
        'provider': provider,
        'thumbnail_url': thumbnail or '',
        'titel': title.strip(),
    }
