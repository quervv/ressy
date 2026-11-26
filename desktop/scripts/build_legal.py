from pathlib import Path

HERE = Path(__file__).resolve().parents[2] / "web"
SITE = "https://www.ressy.top"
ISSUES = "https://github.com/quervv/ressy/issues"

MARK = ('<svg class="mark brand__mark" viewBox="0 0 64 64" aria-hidden="true" focusable="false"><g class="mark__bars">'
        '<rect class="mark__bar" style="--i:0;--h:18" x="4" y="21" width="8" height="18" rx="4"/>'
        '<rect class="mark__bar" style="--i:1;--h:36" x="16" y="12" width="8" height="36" rx="4"/>'
        '<rect class="mark__bar mark__bar--mid" style="--i:2;--h:54" x="28" y="3" width="8" height="54" rx="4"/>'
        '<rect class="mark__bar" style="--i:3;--h:36" x="40" y="12" width="8" height="36" rx="4"/>'
        '<rect class="mark__bar" style="--i:4;--h:18" x="52" y="21" width="8" height="18" rx="4"/></g></svg>')

TWINS = {"privacy": "en/privacy", "cookie": "en/cookies", "termini": "en/terms"}

LANGS = {
    "it": {
        "updated": "Ultimo aggiornamento: 25 novembre 2026",
        "home": "/",
        "home_label": "Ressy, torna alla pagina principale",
        "nav_label": "Documenti legali",
        "pages": [("privacy", "Privacy"), ("cookie", "Cookie"), ("termini", "Termini d’uso")],
        "about": 'Ressy è un progetto indipendente e open source con licenza MIT. '
                 '<a href="https://github.com/quervv/ressy">Codice su GitHub</a>.',
        "prefs": "Preferenze cookie",
        "other": ("en", "EN", "English"),
    },
    "en": {
        "updated": "Last updated: November 25, 2026",
        "home": "/en/",
        "home_label": "Ressy, back to the main page",
        "nav_label": "Legal documents",
        "pages": [("en/privacy", "Privacy"), ("en/cookies", "Cookies"), ("en/terms", "Terms of use")],
        "about": 'Ressy is an independent, open source project under the MIT license. '
                 '<a href="https://github.com/quervv/ressy">Code on GitHub</a>.',
        "prefs": "Cookie preferences",
        "other": ("it", "IT", "Italiano"),
    },
}


def page(lang: str, slug: str, title: str, description: str, body: str) -> str:
    t = LANGS[lang]
    it_slug = slug if lang == "it" else next(k for k, v in TWINS.items() if v == slug)
    en_slug = TWINS[it_slug]
    twin = en_slug if lang == "it" else it_slug
    other, code, name = t["other"]
    nav = "".join(
        f'<a href="/{s}"{" aria-current=\"page\"" if s == slug else ""}>{label}</a>' for s, label in t["pages"])
    links = "".join(f'<a href="/{s}">{label}</a>' for s, label in t["pages"])
    switch = (f'<a class="kc fkey fkey--lang" href="/{twin}" hreflang="{other}" lang="{other}"><span class="kc__face">'
              f'<span class="fkey__sub" aria-hidden="true">{code}</span><span>{name}</span></span></a>')
    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · Ressy</title>
<meta name="description" content="{description}">
<meta name="robots" content="index, follow">
<link rel="canonical" href="{SITE}/{slug}">
<link rel="alternate" hreflang="it" href="{SITE}/{it_slug}">
<link rel="alternate" hreflang="en" href="{SITE}/{en_slug}">
<link rel="alternate" hreflang="x-default" href="{SITE}/{en_slug}">
<meta name="theme-color" content="#17181C">
<meta name="color-scheme" content="dark">
<link rel="icon" href="/favicon.ico" sizes="32x32">
<link rel="icon" href="/assets/ressy-mark.svg" type="image/svg+xml">
<link rel="preload" href="/fonts/archivo-vf.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="/styles.css">
<script src="/boot.js"></script>
<script src="/consent.js" defer></script>
</head>
<body>
<header class="topbar">
  <a class="brand" href="{t["home"]}" aria-label="{t["home_label"]}">
    {MARK}
    <span class="brand__word" aria-hidden="true">ressy</span>
  </a>
  {switch}
</header>
<main class="legal" id="main">
<h1>{title}</h1>
<p class="legal__updated">{t["updated"]}</p>
<nav class="legal__nav" aria-label="{t["nav_label"]}">{nav}</nav>
{body.strip()}
</main>
<footer class="footer">
  <div class="footer__inner">
    <p>{t["about"]}</p>
    <p class="footer__links">{links}<button type="button" class="linklike" data-cookie-settings>{t["prefs"]}</button><a href="/{twin}" hreflang="{other}" lang="{other}">{name}</a></p>
  </div>
</footer>
</body>
</html>
"""


PRIVACY = f"""
<p class="legal__lead">In breve: il sito ressy.top non usa cookie di profilazione e conta le visite in forma anonima solo se lo accetti. L’app Ressy non ha un account, non ha un nostro server e non ci manda niente: le tue chiavi, le impostazioni e le conversazioni restano sul tuo PC o vanno direttamente ai servizi che scegli tu.</p>

<h2>Chi è il titolare</h2>
<p>Il titolare del trattamento dei dati del sito è il progetto Ressy (ressy.top), un progetto open source indipendente. Per domande sulla privacy o per esercitare i tuoi diritti scrivi aprendo una segnalazione su <a href="{ISSUES}">GitHub</a> (non inserire lì dati personali: ti risponderemo indicando un canale privato).</p>

<h2>Il sito ressy.top</h2>
<h3>Hosting e registri tecnici</h3>
<p>Il sito è ospitato da Vercel Inc. Come ogni server web, Vercel tratta l’indirizzo IP, il tipo di browser e la pagina richiesta per consegnare le pagine, proteggerle dagli abusi e tenere brevi registri tecnici. Base giuridica: legittimo interesse a far funzionare il sito in modo sicuro (art. 6.1.f GDPR). Vercel può trattare dati anche negli Stati Uniti, con le garanzie previste (Data Privacy Framework e clausole contrattuali standard).</p>
<h3>Statistiche anonime (solo con il tuo consenso)</h3>
<p>Se premi «Accetta» nel banner usiamo Vercel Web Analytics per sapere quante persone visitano le pagine, da quale sito arrivano, da quale Paese e con quale tipo di dispositivo. Non usa cookie, non crea un profilo e non ti riconosce su altri siti; i dati sono aggregati. Base giuridica: il tuo consenso (art. 6.1.a GDPR), che puoi ritirare quando vuoi da «Preferenze cookie» in fondo a ogni pagina.</p>
<h3>Microfono nella prova della pagina</h3>
<p>Se usi la prova vocale della pagina principale, il browser ti chiede il permesso del microfono. L’audio viene analizzato solo nel tuo browser per disegnare il livello della voce: non viene registrato né inviato a nessuno.</p>
<h3>Download</h3>
<p>Il file di installazione viene scaricato dal sito o da GitHub (GitHub, Inc.), che tratta l’IP e i dati tecnici necessari al download secondo la propria informativa.</p>
<h3>Area di amministrazione</h3>
<p>La pagina /admin è riservata al gestore del sito e usa un cookie tecnico di sessione solo per chi vi accede con la password. I visitatori non la usano.</p>

<h2>L’app Ressy per Windows</h2>
<p>L’app gira sul tuo PC. Non c’è un account Ressy e il progetto non riceve i tuoi comandi, le tue conversazioni o le tue chiavi. Ressy contatta altri servizi solo per fare quello che le chiedi e solo quelli che hai scelto tu:</p>
<ul>
  <li><b>Intelligenza artificiale</b>: con le tue chiavi, Groq, Google Gemini, OpenRouter o Anthropic (Claude) ricevono le tue richieste e i dati che servono a rispondere (per esempio il testo letto sullo schermo quando chiedi «cosa c’è sullo schermo?»). Con l’AI sul PC (llama.cpp) non esce niente.</li>
  <li><b>Voce</b>: il riconoscimento vocale avviene sul PC con il modello locale, oppure con Groq o Gemini se li scegli. La voce di Ressy usa la sintesi vocale online di Microsoft Edge oppure quella di Windows, offline.</li>
  <li><b>Telegram e Discord</b>: se colleghi il tuo bot, i messaggi che gli mandi passano da Telegram o Discord secondo le loro regole.</li>
  <li><b>Meteo</b>: Open-Meteo riceve la città che chiedi; se non dici la città, ipapi.co stima la tua zona dall’indirizzo IP.</li>
  <li><b>Modelli e aggiornamenti</b>: i modelli per la voce e per l’AI sul PC si scaricano da Hugging Face; Ressy controlla su GitHub se c’è una versione nuova. Queste richieste contengono solo i dati tecnici del download.</li>
</ul>
<p>Le chiavi e i token sono salvati sul tuo PC e cifrati con Windows (DPAPI), legati al tuo utente. Il registro dell’app (ressy.log) resta sul PC. Disinstallando Ressy puoi cancellare tutto.</p>

<h2>Per quanto tempo</h2>
<p>I registri tecnici dell’hosting sono conservati per il tempo breve previsto da Vercel. Le statistiche sono aggregate e anonime. Sul sito non conserviamo altri dati personali.</p>

<h2>I tuoi diritti</h2>
<p>Hai diritto di chiedere accesso, rettifica, cancellazione, limitazione e opposizione al trattamento, di ritirare il consenso in ogni momento e di proporre reclamo al Garante per la protezione dei dati personali (<a href="https://www.garanteprivacy.it">garanteprivacy.it</a>).</p>

<h2>Minori</h2>
<p>Il sito e l’app non sono pensati per chi ha meno di 14 anni. I servizi AI che colleghi hanno i loro limiti di età.</p>

<h2>Modifiche</h2>
<p>Se questa informativa cambia, aggiorniamo la data in cima alla pagina.</p>
"""

COOKIE = """
<p class="legal__lead">Il sito ressy.top non usa cookie di profilazione né pubblicità. Ecco esattamente cosa salva nel tuo browser.</p>

<h2>Cosa usiamo</h2>
<div class="table-wrap">
<table>
  <thead><tr><th scope="col">Nome</th><th scope="col">Tipo</th><th scope="col">A cosa serve</th><th scope="col">Durata</th></tr></thead>
  <tbody>
    <tr><td><code>ressy-consent</code></td><td>Archivio locale del browser (tecnico)</td><td>Ricorda la tua scelta nel banner, così non te lo chiediamo a ogni visita.</td><td>Finché non cancelli i dati del sito</td></tr>
    <tr><td>Vercel Web Analytics</td><td>Statistica anonima, senza cookie</td><td>Conta le visite in forma aggregata. Parte solo se premi «Accetta».</td><td>Nessun dato nel browser</td></tr>
    <tr><td><code>ressy_admin</code></td><td>Cookie tecnico di sessione</td><td>Solo per il gestore che entra in /admin con la password.</td><td>12 ore</td></tr>
  </tbody>
</table>
</div>

<h2>Il consenso</h2>
<p>Al primo accesso il banner ti chiede se accetti le statistiche anonime. «Solo necessari» le lascia spente: il sito funziona comunque in tutte le sue parti. Puoi cambiare idea in ogni momento:</p>
<p><button type="button" class="consent__btn consent__btn--primary" data-cookie-settings>Apri le preferenze cookie</button></p>

<h2>Come cancellare i dati dal browser</h2>
<p>Puoi cancellare la scelta salvata e ogni altro dato del sito dalle impostazioni del browser (cronologia o «dati dei siti»). Al prossimo accesso il banner ricomparirà.</p>

<p>Per il resto del trattamento dei dati leggi la <a href="/privacy">privacy</a>.</p>
"""

TERMS = f"""
<p class="legal__lead">Ressy è software libero, distribuito gratuitamente con licenza MIT. Usandolo accetti queste condizioni.</p>

<h2>Licenza</h2>
<p>Il codice di Ressy è pubblicato su <a href="https://github.com/quervv/ressy">GitHub</a> con licenza MIT: puoi usarlo, copiarlo, modificarlo e distribuirlo, mantenendo l’avviso di copyright e la licenza.</p>

<h2>Nessuna garanzia</h2>
<p>Ressy è fornito «così com’è», senza garanzie di alcun tipo. Nei limiti consentiti dalla legge, gli autori non rispondono di danni derivanti dall’uso del programma. Restano salvi i diritti che la legge riconosce in modo inderogabile ai consumatori.</p>

<h2>Uso responsabile</h2>
<ul>
  <li>Ressy agisce sul tuo PC con i tuoi permessi: apre programmi, scrive file e messaggi, esegue comandi. Controlla quello che le chiedi di fare, soprattutto da remoto.</li>
  <li>Proteggi il tuo bot Telegram o Discord: chi lo controlla può dare comandi al tuo PC. Collega solo i tuoi account.</li>
  <li>Non usare Ressy per violare la legge, i diritti di altre persone o le regole dei servizi che usi (per esempio inviare spam su Discord).</li>
</ul>

<h2>Servizi di terze parti</h2>
<p>Ressy usa servizi di altri (Groq, Google Gemini, OpenRouter, Anthropic, Microsoft, Telegram, Discord, Open-Meteo, GitHub, Hugging Face) con le tue chiavi e i tuoi account. Ciascuno ha le sue condizioni, i suoi limiti e i suoi eventuali costi, che accetti direttamente con loro. Ressy non è affiliato a nessuno di questi servizi, né a Marvel.</p>

<h2>Risposte dell’intelligenza artificiale</h2>
<p>Le risposte di Ressy sono generate da modelli di AI e possono essere sbagliate o incomplete. Non usarle come unico riferimento per decisioni mediche, legali, finanziarie o di sicurezza.</p>

<h2>Il sito</h2>
<p>I testi e la grafica di ressy.top appartengono al progetto Ressy. I marchi citati appartengono ai rispettivi titolari.</p>

<h2>Contatti e modifiche</h2>
<p>Per segnalazioni usa <a href="{ISSUES}">GitHub</a>. Se queste condizioni cambiano, aggiorniamo la data in cima alla pagina. Si applica la legge italiana, salvi i diritti inderogabili del consumatore.</p>
"""

PRIVACY_EN = f"""
<p class="legal__lead">In short: the ressy.top site uses no profiling cookies and counts visits anonymously only if you accept. The Ressy app has no account, no server of ours and sends us nothing: your keys, your settings and your conversations stay on your PC or go straight to the services you choose.</p>

<h2>Who is the controller</h2>
<p>The controller of the site’s data is the Ressy project (ressy.top), an independent open source project. For privacy questions or to exercise your rights, open an issue on <a href="{ISSUES}">GitHub</a> (don’t put personal data there: we’ll reply with a private channel).</p>

<h2>The ressy.top site</h2>
<h3>Hosting and technical logs</h3>
<p>The site is hosted by Vercel Inc. Like any web server, Vercel processes the IP address, the browser type and the requested page to deliver the pages, protect them from abuse and keep short technical logs. Legal basis: legitimate interest in running the site securely (Art. 6(1)(f) GDPR). Vercel may also process data in the United States, with the required safeguards (Data Privacy Framework and standard contractual clauses).</p>
<h3>Anonymous statistics (only with your consent)</h3>
<p>If you press “Accept” in the banner, we use Vercel Web Analytics to know how many people visit the pages, which site they come from, from which country and with which type of device. It uses no cookies, builds no profile and doesn’t recognize you on other sites; the data is aggregated. Legal basis: your consent (Art. 6(1)(a) GDPR), which you can withdraw at any time from “Cookie preferences” at the bottom of every page.</p>
<h3>Microphone in the page’s demo</h3>
<p>If you use the voice demo on the main page, the browser asks you for permission to use the microphone. The audio is analyzed only in your browser to draw the level of your voice: it isn’t recorded or sent to anyone.</p>
<h3>Downloads</h3>
<p>The installation file is downloaded from the site or from GitHub (GitHub, Inc.), which processes the IP address and the technical data needed for the download under its own privacy policy.</p>
<h3>Administration area</h3>
<p>The /admin page is reserved for the site’s operator and uses a technical session cookie only for whoever signs in with the password. Visitors don’t use it.</p>

<h2>The Ressy app for Windows</h2>
<p>The app runs on your PC. There is no Ressy account and the project doesn’t receive your commands, your conversations or your keys. Ressy contacts other services only to do what you ask, and only the ones you chose:</p>
<ul>
  <li><b>Artificial intelligence</b>: with your keys, Groq, Google Gemini, OpenRouter or Anthropic (Claude) receive your requests and the data needed to answer (for example the text read on the screen when you ask “what’s on the screen?”). With the AI on your PC (llama.cpp) nothing leaves the PC.</li>
  <li><b>Voice</b>: speech recognition happens on the PC with the local model, or with Groq or Gemini if you choose them. Ressy’s voice uses Microsoft Edge’s online speech synthesis or the Windows one, offline.</li>
  <li><b>Telegram and Discord</b>: if you link your bot, the messages you send it go through Telegram or Discord under their rules.</li>
  <li><b>Weather</b>: Open-Meteo receives the city you ask about; if you don’t name a city, ipapi.co estimates your area from your IP address.</li>
  <li><b>Models and updates</b>: the speech models and the AI for the PC are downloaded from Hugging Face; Ressy checks GitHub for a new version. These requests contain only the technical data of the download.</li>
</ul>
<p>Keys and tokens are saved on your PC, encrypted with Windows (DPAPI) and tied to your user. The app’s log (ressy.log) stays on the PC. When you uninstall Ressy you can delete everything.</p>

<h2>How long</h2>
<p>The hosting’s technical logs are kept for the short time set by Vercel. The statistics are aggregated and anonymous. We keep no other personal data on the site.</p>

<h2>Your rights</h2>
<p>You have the right to request access, rectification, erasure, restriction of processing and to object to it, to withdraw your consent at any time and to lodge a complaint with a supervisory authority: in Italy the Garante per la protezione dei dati personali (<a href="https://www.garanteprivacy.it">garanteprivacy.it</a>), or the authority of the country where you live or work.</p>

<h2>Children</h2>
<p>The site and the app aren’t meant for people under 14. The AI services you connect have their own age limits.</p>

<h2>Changes</h2>
<p>If this policy changes, we update the date at the top of the page.</p>
"""

COOKIE_EN = """
<p class="legal__lead">The ressy.top site uses no profiling cookies and no advertising. Here is exactly what it saves in your browser.</p>

<h2>What we use</h2>
<div class="table-wrap">
<table>
  <thead><tr><th scope="col">Name</th><th scope="col">Type</th><th scope="col">What it’s for</th><th scope="col">Duration</th></tr></thead>
  <tbody>
    <tr><td><code>ressy-consent</code></td><td>Browser local storage (technical)</td><td>Remembers your choice in the banner, so we don’t ask you at every visit.</td><td>Until you clear the site’s data</td></tr>
    <tr><td>Vercel Web Analytics</td><td>Anonymous statistics, no cookies</td><td>Counts visits in aggregate. It starts only if you press “Accept”.</td><td>No data in the browser</td></tr>
    <tr><td><code>ressy_admin</code></td><td>Technical session cookie</td><td>Only for the operator who signs in to /admin with the password.</td><td>12 hours</td></tr>
  </tbody>
</table>
</div>

<h2>Consent</h2>
<p>On your first visit the banner asks whether you accept the anonymous statistics. “Necessary only” leaves them off: every part of the site works anyway. You can change your mind at any time:</p>
<p><button type="button" class="consent__btn consent__btn--primary" data-cookie-settings>Open cookie preferences</button></p>

<h2>How to delete the data from your browser</h2>
<p>You can delete the saved choice and any other data of the site from your browser’s settings (history or “site data”). On your next visit the banner will show up again.</p>

<p>For everything else about how data is processed, read the <a href="/en/privacy">privacy policy</a>.</p>
"""

TERMS_EN = f"""
<p class="legal__lead">Ressy is free software, distributed at no cost under the MIT license. By using it you accept these terms.</p>

<h2>License</h2>
<p>Ressy’s code is published on <a href="https://github.com/quervv/ressy">GitHub</a> under the MIT license: you can use, copy, modify and distribute it, keeping the copyright notice and the license.</p>

<h2>No warranty</h2>
<p>Ressy is provided “as is”, without warranties of any kind. To the extent permitted by law, the authors aren’t liable for damages arising from the use of the program. This doesn’t affect the rights that the law grants consumers and that can’t be waived.</p>

<h2>Responsible use</h2>
<ul>
  <li>Ressy acts on your PC with your permissions: it opens programs, writes files and messages, runs commands. Check what you ask Ressy to do, especially remotely.</li>
  <li>Protect your Telegram or Discord bot: whoever controls it can give commands to your PC. Link only your own accounts.</li>
  <li>Don’t use Ressy to break the law, other people’s rights or the rules of the services you use (for example to send spam on Discord).</li>
</ul>

<h2>Third-party services</h2>
<p>Ressy uses other parties’ services (Groq, Google Gemini, OpenRouter, Anthropic, Microsoft, Telegram, Discord, Open-Meteo, GitHub, Hugging Face) with your keys and your accounts. Each one has its own terms, limits and any costs, which you accept directly with them. Ressy isn’t affiliated with any of these services, nor with Marvel.</p>

<h2>Answers from the artificial intelligence</h2>
<p>Ressy’s answers are generated by AI models and may be wrong or incomplete. Don’t use them as your only reference for medical, legal, financial or safety decisions.</p>

<h2>The site</h2>
<p>The texts and graphics of ressy.top belong to the Ressy project. The trademarks mentioned belong to their respective owners.</p>

<h2>Contact and changes</h2>
<p>For reports use <a href="{ISSUES}">GitHub</a>. If these terms change, we update the date at the top of the page. Italian law applies, without prejudice to the consumer’s mandatory rights.</p>
"""

for lang, slug, title, desc, body in [
    ("it", "privacy", "Privacy", "Come Ressy e il sito ressy.top trattano i dati: niente account, niente profilazione, le chiavi restano sul tuo PC.", PRIVACY),
    ("it", "cookie", "Cookie", "I cookie e i dati che il sito ressy.top salva nel browser, e come cambiare il consenso.", COOKIE),
    ("it", "termini", "Termini d’uso", "Le condizioni d’uso di Ressy, l’assistente vocale open source per Windows con licenza MIT.", TERMS),
    ("en", "en/privacy", "Privacy", "How Ressy and the ressy.top site handle data: no account, no profiling, your keys stay on your PC.", PRIVACY_EN),
    ("en", "en/cookies", "Cookies", "The cookies and data the ressy.top site saves in your browser, and how to change your consent.", COOKIE_EN),
    ("en", "en/terms", "Terms of use", "The terms of use of Ressy, the open source voice assistant for Windows under the MIT license.", TERMS_EN),
]:
    target = HERE / f"{slug}.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(page(lang, slug, title, desc, body), encoding="utf-8")
print("ok")
