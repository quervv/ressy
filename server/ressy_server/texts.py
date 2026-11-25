from __future__ import annotations

PLATFORM_LABEL = {"telegram": "Telegram", "discord": "Discord"}


def cmd(platform: str, name: str) -> str:
    return f"/{name}" if platform == "telegram" else f"!{name}"


def welcome(platform: str, public_url: str) -> str:
    return (
        "👋 Ciao! Sono il bot di Ressy.\n\n"
        "Da qui comandi Ressy sul tuo PC anche quando sei lontano: scrivimi o mandami un vocale, "
        "lei esegue e ti risponde.\n\n"
        "Per iniziare:\n"
        f"1. Installa Ressy sul PC ({public_url})\n"
        f"2. Sul PC clicca l'icona di Ressy accanto all'orologio → «Collega Telegram o Discord»\n"
        f"3. Inviami il codice che vedi: {cmd(platform, 'collega')} CODICE\n\n"
        f"Comandi: {cmd(platform, 'aiuto')}"
    )


def help_text(platform: str) -> str:
    c = lambda n: cmd(platform, n)
    return (
        "🤖 Come funziona\n"
        "Scrivi (o manda un vocale) quello che vuoi far fare al tuo PC, per esempio:\n"
        "• apri Spotify\n"
        "• scrivi su Discord a Marco che arrivo tra dieci minuti\n"
        "• fammi uno screenshot\n"
        "• abbassa il volume al 30%\n"
        "• ricordami tra 20 minuti di togliere la pizza\n\n"
        "Comandi:\n"
        f"{c('collega')} CODICE — collega questo account al tuo PC\n"
        f"{c('stato')} — stato del PC e delle preferenze\n"
        f"{c('voce')} sempre | auto | mai — risposte vocali\n"
        f"{c('notifiche')} on | off — avvisi quando il PC va offline/online\n"
        f"{c('scollega')} — scollega questo account\n\n"
        "Se Ressy non è attiva sul PC te lo dico subito: in quel caso il comando non viene eseguito."
    )


LINK_USAGE = "Inviami il codice che vedi nell'app Ressy, per esempio: {command} K7P2QX"
LINK_BAD = (
    "❌ Codice non valido o scaduto.\n"
    "Generane uno nuovo sul PC (icona di Ressy → «Collega Telegram o Discord») e riprova."
)
LINK_RATE = "⏳ Troppi tentativi con codici errati. Riprova tra qualche minuto."
NOT_LINKED = (
    "🔗 Questo account non è ancora collegato a nessun PC.\n"
    "Sul PC clicca l'icona di Ressy → «Collega Telegram o Discord», poi inviami il codice con {command} CODICE."
)
RATE_LIMIT = "🐢 Stai inviando troppi comandi: aspetta qualche secondo e riprova."
STALE = (
    "⏳ Questo messaggio è arrivato mentre il bot era irraggiungibile, quindi non lo eseguo "
    "(per sicurezza non eseguo comandi in ritardo). Rimandalo se ti serve ancora."
)
TIMEOUT = "⏱️ Ressy non ha risposto in tempo: il comando potrebbe essere stato eseguito solo in parte."
DISCONNECTED_DURING = (
    "⚠️ Ressy si è disconnessa mentre eseguiva il comando: non so se è stato completato."
)
AUDIO_TOO_LARGE = "🎙️ Il vocale è troppo lungo: il massimo è 5 minuti."
UNSUPPORTED = "Per ora capisco solo messaggi di testo e vocali 🙂"
EMPTY_REPLY = "✅ Fatto."
AGENT_ERROR = "⚠️ Ressy ha avuto un problema nell'eseguire il comando."
INTERNAL_ERROR = "⚠️ Si è verificato un errore interno del bot. Riprova tra poco."


def link_ok(pc_name: str, online: bool) -> str:
    state = (
        "🟢 Il PC è online: puoi già darle comandi."
        if online
        else "🔴 Il PC ora è offline: i comandi funzioneranno quando Ressy sarà attiva."
    )
    return (
        f"✅ Collegato a Ressy sul PC «{pc_name}».\n{state}\n\n"
        "Prova a scrivermi «apri Spotify» oppure «fammi uno screenshot»."
    )


def offline(pc_name: str, last_seen: str) -> str:
    return (
        f"🔴 Offline: Ressy non è attiva sul tuo PC «{pc_name}» (ultimo contatto: {last_seen}).\n"
        "Il comando NON verrà eseguito. Avvia Ressy sul PC e riprova."
    )


def offline_notice(pc_name: str) -> str:
    return (
        f"🔴 Offline: Ressy si è disconnessa dal PC «{pc_name}».\n"
        "Finché non torna online i comandi non verranno eseguiti: ti avviso io quando rientra."
    )


def quit_notice(pc_name: str) -> str:
    return (
        f"🔴 Offline: Ressy è stata chiusa sul PC «{pc_name}».\n"
        "I comandi non verranno eseguiti finché non la riavvii."
    )


def online_notice(pc_name: str) -> str:
    return f"🟢 Online: Ressy è di nuovo online sul PC «{pc_name}», puoi darle comandi."


def status(pc_name: str, online: bool, last_seen: str, presence_alerts: bool, voice_mode: int) -> str:
    voice = {0: "auto (solo se mandi un vocale)", 1: "sempre", 2: "mai"}.get(voice_mode, "auto")
    state = "🟢 Online" if online else f"🔴 Offline (ultimo contatto: {last_seen})"
    return (
        f"🖥️ PC collegato: «{pc_name}»\n"
        f"Stato: {state}\n"
        f"Avvisi online/offline: {'attivi' if presence_alerts else 'disattivati'}\n"
        f"Risposte vocali: {voice}"
    )


def unlinked(pc_name: str) -> str:
    return (
        f"🔌 Account scollegato dal PC «{pc_name}».\n"
        "Puoi ricollegarlo quando vuoi con un nuovo codice dall'app."
    )


def unlinked_by_pc(pc_name: str) -> str:
    return f"🔌 Il PC «{pc_name}» ha scollegato questo account: non riceverà più i tuoi comandi."


def moved(pc_name: str) -> str:
    return f"🔁 Questo account ora comanda il PC «{pc_name}»."


def presence_set(on: bool) -> str:
    return (
        "🔔 Avvisi attivi: ti scrivo quando Ressy va offline o torna online."
        if on
        else "🔕 Avvisi disattivati: non ti scriverò quando Ressy va offline o torna online."
    )


def voice_set(mode: int) -> str:
    return {
        0: "🎙️ Risposte vocali in automatico: ti rispondo a voce quando mi mandi un vocale.",
        1: "🎙️ Ti risponderò sempre anche a voce.",
        2: "💬 Ti risponderò solo per iscritto.",
    }.get(mode, "🎙️ Risposte vocali in automatico.")


def voice_usage(platform: str, mode: int) -> str:
    return f"{voice_set(mode)}\nCambia con: {cmd(platform, 'voce')} sempre | auto | mai"


def presence_usage(platform: str, on: bool) -> str:
    return f"{presence_set(on)}\nCambia con: {cmd(platform, 'notifiche')} on | off"


NOT_LINKED_SHORT = "🔗 Nessun PC collegato a questo account."


def intruder_alert(platform: str, display: str, user_id: str) -> str:
    return (
        f"🚫 Qualcuno ha provato a usare il tuo bot su {PLATFORM_LABEL.get(platform, platform)}: "
        f"{display} (id {user_id}).\n"
        "L'ho bloccato e ho cancellato la chat con lui. Il bot risponde solo a te."
    )
