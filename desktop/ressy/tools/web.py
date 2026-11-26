from __future__ import annotations

import html as html_lib
import ipaddress
import json
import logging
import re
import socket
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
    "ebay": "https://www.ebay.it",
    "subito": "https://www.subito.it",
    "github": "https://github.com",
    "stackoverflow": "https://stackoverflow.com",
    "instagram": "https://www.instagram.com",
    "facebook": "https://www.facebook.com",
    "wikipedia": "https://it.wikipedia.org",
    "chatgpt": "https://chatgpt.com",
    "claude": "https://claude.ai",
    "gemini": "https://gemini.google.com",
    "perplexity": "https://www.perplexity.ai",
    "maps": "https://maps.google.com",
    "google maps": "https://maps.google.com",
    "drive": "https://drive.google.com",
    "calendar": "https://calendar.google.com",
    "translate": "https://translate.google.com",
    "traduttore": "https://translate.google.com",
    "speedtest": "https://www.speedtest.net",
    "ansa": "https://www.ansa.it",
    "repubblica": "https://www.repubblica.it",
    "corriere": "https://www.corriere.it",
    "x": "https://x.com",
    "twitter": "https://x.com",
    "reddit": "https://www.reddit.com",
    "linkedin": "https://www.linkedin.com",
    "whatsapp web": "https://web.whatsapp.com",
    "telegram web": "https://web.telegram.org",
    "discord web": "https://discord.com/app",
    "spotify web": "https://open.spotify.com",
    "spotify": "https://open.spotify.com",
    "outlook": "https://outlook.live.com",
    "disney plus": "https://www.disneyplus.com",
    "disney+": "https://www.disneyplus.com",
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


_SEARCH_URLS = {
    "google": ("Google", "https://www.google.com/search?q={q}"),
    "images": ("Google Immagini", "https://www.google.com/search?tbm=isch&q={q}"),
    "youtube": ("YouTube", "https://www.youtube.com/results?search_query={q}"),
    "amazon": ("Amazon", "https://www.amazon.it/s?k={q}"),
    "wikipedia": ("Wikipedia", "https://it.wikipedia.org/w/index.php?search={q}"),
    "maps": ("Google Maps", "https://www.google.com/maps/search/{q}"),
    "github": ("GitHub", "https://github.com/search?q={q}"),
    "reddit": ("Reddit", "https://www.reddit.com/search/?q={q}"),
    "translate": ("Google Traduttore", "https://translate.google.com/?sl=auto&tl=it&text={q}"),
}


def web_search(ctx: ToolContext, args: dict) -> str:
    query = args["query"].strip()
    if not query:
        raise ToolError(tr("Cosa devo cercare?"))
    site = (args.get("site") or "google").strip().lower()
    label, template = _SEARCH_URLS.get(site, _SEARCH_URLS["google"])
    _open(template.format(q=urllib.parse.quote_plus(query)))
    return tr("Ho cercato «{query}» su {site} nel browser.").format(query=query, site=label)


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


def _check_public_host(url: str) -> None:
    host = (urllib.parse.urlparse(url).hostname or "").strip().lower()
    if not host or host in ("localhost", "ip6-localhost") or host.endswith(".local"):
        raise ToolError(tr("Non posso aprire indirizzi locali o privati."))
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise ToolError(tr("Non riesco a trovare il sito {host}.").format(host=host)) from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ToolError(tr("Non posso aprire indirizzi locali o privati."))


_STRIP_BLOCKS = re.compile(r"<(script|style|noscript|svg|head)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_HTML_TAGS = re.compile(r"<[^>]+>")


def read_webpage(ctx: ToolContext, args: dict) -> str:
    url = normalize_url(args["url"])
    _check_public_host(url)
    try:
        response = httpx.get(
            url,
            headers={"User-Agent": _UA, "Accept-Language": "it-IT,it;q=0.9,en;q=0.6"},
            timeout=10.0,
            follow_redirects=True,
        )
        _check_public_host(str(response.url))
        response.raise_for_status()
    except ToolError:
        raise
    except httpx.HTTPError as exc:
        raise ToolError(tr("Non sono riuscita a leggere la pagina ({exc}).").format(exc=type(exc).__name__)) from exc
    body = response.text
    text = _STRIP_BLOCKS.sub(" ", body)
    text = re.sub(r"</(?:p|div|li|h[1-6]|tr|br)[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = _HTML_TAGS.sub(" ", text)
    text = html_lib.unescape(text)
    lines = [" ".join(line.split()) for line in text.splitlines()]
    cleaned = "\n".join(line for line in lines if line)
    if not cleaned:
        return tr("La pagina non contiene testo leggibile.")
    return cleaned[:5000]


def compose_email(ctx: ToolContext, args: dict) -> str:
    to = (args.get("to") or "").strip()
    subject = (args.get("subject") or "").strip()
    body = (args.get("body") or "").strip()
    params_q = {}
    if subject:
        params_q["subject"] = subject
    if body:
        params_q["body"] = body
    query = urllib.parse.urlencode(params_q, quote_via=urllib.parse.quote)
    uri = f"mailto:{urllib.parse.quote(to)}" + (f"?{query}" if query else "")
    _open(uri)
    return tr("Ho preparato la bozza email{to}.").format(to=tr(" per {to}").format(to=to) if to else "")


TOOLS = [
    Tool(
        "open_url",
        "Apre un sito nel browser predefinito (indirizzo o nome noto, es. youtube, gmail).",
        params({"url": {"type": "string"}}, ["url"]),
        open_url,
    ),
    Tool(
        "web_search",
        "Cerca nel browser su Google, YouTube, Amazon, Wikipedia, Maps, GitHub, Reddit, Translate o Immagini.",
        params(
            {
                "query": {"type": "string"},
                "site": {
                    "type": "string",
                    "enum": ["google", "images", "youtube", "amazon", "wikipedia", "maps", "github", "reddit", "translate"],
                },
            },
            ["query"],
        ),
        web_search,
    ),
    Tool(
        "read_webpage",
        "Scarica e legge il testo di una pagina web (per riassumerla o estrarne informazioni).",
        params({"url": {"type": "string"}}, ["url"]),
        read_webpage,
        timeout=20,
    ),
    Tool(
        "compose_email",
        "Apre una nuova bozza email nel client di posta con destinatario, oggetto e testo.",
        params(
            {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            }
        ),
        compose_email,
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
