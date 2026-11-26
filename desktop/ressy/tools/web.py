from __future__ import annotations

import json
import logging
import re
import urllib.parse
import webbrowser

import httpx

from .registry import Tool, ToolContext, ToolError, params
from ..i18n import language, tr

log = logging.getLogger("ressy.web")

_DOMAIN = re.compile(r"^[\w.-]+\.[a-z]{2,24}(?:[/:?#].*)?$", re.IGNORECASE)
_VIDEO = re.compile(r'"videoRenderer":\{"videoId":"([A-Za-z0-9_-]{11})"')
_TITLE = re.compile(r'"title":\{"runs":\[\{"text":"((?:[^"\\]|\\.)*)"')
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

SITES = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "netflix": "https://www.netflix.com",
    "twitch": "https://www.twitch.tv",
    "amazon": "https://www.amazon.it",
    "github": "https://github.com",
    "instagram": "https://www.instagram.com",
    "facebook": "https://www.facebook.com",
    "wikipedia": "https://it.wikipedia.org",
    "chatgpt": "https://chatgpt.com",
    "maps": "https://maps.google.com",
    "google maps": "https://maps.google.com",
    "drive": "https://drive.google.com",
    "x": "https://x.com",
    "twitter": "https://x.com",
    "reddit": "https://www.reddit.com",
    "linkedin": "https://www.linkedin.com",
    "whatsapp web": "https://web.whatsapp.com",
    "telegram web": "https://web.telegram.org",
    "discord web": "https://discord.com/app",
    "spotify web": "https://open.spotify.com",
}


def normalize_url(raw: str) -> str:
    text = raw.strip()
    key = text.lower().rstrip("/")
    if key in SITES:
        return SITES[key]
    parsed = urllib.parse.urlparse(text)
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return text
    if parsed.scheme and parsed.scheme not in ("http", "https") and "." not in parsed.scheme:
        raise ToolError(tr("Apro solo indirizzi web (http/https)."))
    if " " not in text and _DOMAIN.match(text):
        return "https://" + text
    raise ToolError(tr("'{raw}' non sembra un indirizzo web.").format(raw=raw))


def _open(url: str) -> None:
    if not webbrowser.open(url, new=2):
        raise ToolError(tr("Non riesco ad aprire il browser predefinito."))


def open_url(ctx: ToolContext, args: dict) -> str:
    url = normalize_url(args["url"])
    _open(url)
    return tr("Ho aperto {value} nel browser.").format(value=urllib.parse.urlparse(url).netloc or url)


def web_search(ctx: ToolContext, args: dict) -> str:
    query = args["query"].strip()
    if not query:
        raise ToolError(tr("Cosa devo cercare?"))
    _open("https://www.google.com/search?q=" + urllib.parse.quote_plus(query))
    return tr("Ho cercato «{query}» su Google nel browser.").format(query=query)


def first_youtube_video(html: str) -> tuple[str, str] | None:
    match = _VIDEO.search(html)
    if match is None:
        return None
    title = ""
    title_match = _TITLE.search(html, match.end())
    if title_match is not None:
        try:
            title = json.loads(f'"{title_match.group(1)}"')
        except ValueError:
            title = ""
    return match.group(1), title


def play_youtube(ctx: ToolContext, args: dict) -> str:
    query = args["query"].strip()
    if not query:
        raise ToolError(tr("Cosa devo cercare su YouTube?"))
    results_url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)
    found = None
    try:
        response = httpx.get(
            results_url,
            headers={"User-Agent": _UA, "Accept-Language": "en-US,en;q=0.9,it;q=0.5" if language() == "en"
                     else "it-IT,it;q=0.9,en;q=0.6"},
            timeout=8.0,
            follow_redirects=True,
        )
        if response.status_code == 200 and "consent." not in str(response.url):
            found = first_youtube_video(response.text)
    except httpx.HTTPError:
        log.info("YouTube lookup failed, opening the results page", exc_info=True)
    if found is None:
        _open(results_url)
        return tr("Ho aperto i risultati di YouTube per «{query}»: scegli tu il video.").format(query=query)
    video_id, title = found
    _open(f"https://www.youtube.com/watch?v={video_id}")
    return tr("Riproduco su YouTube: {title}.").format(title=title) if title else tr("Riproduco su YouTube il primo risultato per «{query}».").format(query=query)


async def web_answer(ctx: ToolContext, args: dict) -> str:
    question = args["question"].strip()
    if not question:
        raise ToolError(tr("Qual è la domanda?"))
    answer = await ctx.services.llm.web_answer(question, language=ctx.services.settings.language)
    if not answer:
        raise ToolError(tr("La ricerca non ha dato risultati utili."))
    return answer


TOOLS = [
    Tool(
        "open_url",
        "Apre un sito nel browser predefinito (indirizzo o nome noto, es. youtube, gmail).",
        params({"url": {"type": "string"}}, ["url"]),
        open_url,
    ),
    Tool(
        "web_search",
        "Apre una ricerca Google nel browser (quando l'utente vuole vedere i risultati).",
        params({"query": {"type": "string"}}, ["query"]),
        web_search,
    ),
    Tool(
        "play_youtube",
        "Cerca su YouTube e avvia il primo video (musica, video, tutorial).",
        params({"query": {"type": "string"}}, ["query"]),
        play_youtube,
        timeout=20,
    ),
    Tool(
        "web_answer",
        "Cerca sul web e restituisce una risposta aggiornata (notizie, meteo, risultati, prezzi, fatti recenti).",
        params({"question": {"type": "string"}}, ["question"]),
        web_answer,
        timeout=60,
    ),
]
