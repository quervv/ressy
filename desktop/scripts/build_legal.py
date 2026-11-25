from pathlib import Path

HERE = Path(__file__).resolve().parents[2] / "web"
UPDATED = "25 novembre 2026"
ISSUES = "https://github.com/quervv/ressy/issues"

MARK = ('<svg class="mark brand__mark" viewBox="0 0 64 64" aria-hidden="true" focusable="false"><g class="mark__bars">'
        '<rect class="mark__bar" style="--i:0;--h:18" x="4" y="21" width="8" height="18" rx="4"/>'
        '<rect class="mark__bar" style="--i:1;--h:36" x="16" y="12" width="8" height="36" rx="4"/>'
        '<rect class="mark__bar mark__bar--mid" style="--i:2;--h:54" x="28" y="3" width="8" height="54" rx="4"/>'
        '<rect class="mark__bar" style="--i:3;--h:36" x="40" y="12" width="8" height="36" rx="4"/>'
        '<rect class="mark__bar" style="--i:4;--h:18" x="52" y="21" width="8" height="18" rx="4"/></g></svg>')

PAGES = [("privacy", "Privacy"), ("cookie", "Cookie"), ("termini", "Termini d’uso")]


def page(slug: str, title: str, description: str, body: str) -> str:
    nav = "".join(
        f'<a href="/{s}"{" aria-current=\"page\"" if s == slug else ""}>{label}</a>' for s, label in PAGES)
    return f"""<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · Ressy</title>
<meta name="description" content="{description}">
<meta name="robots" content="index, follow">
<link rel="canonical" href="https://www.ressy.top/{slug}">
<meta name="theme-color" content="#17181C">
<meta name="color-scheme" content="dark">
<link rel="icon" href="favicon.ico" sizes="32x32">
<link rel="icon" href="assets/ressy-mark.svg" type="image/svg+xml">
<link rel="preload" href="fonts/archivo-vf.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="styles.css">
<script src="boot.js"></script>
<script src="consent.js" defer></script>
</head>
<body>
<header class="topbar">
  <a class="brand" href="/" aria-label="Ressy, torna alla pagina principale">
    {MARK}
    <span class="brand__word" aria-hidden="true">ressy</span>
  </a>
</header>
<main class="legal" id="main">
<h1>{title}</h1>
<p class="legal__updated">Ultimo aggiornamento: {UPDATED}</p>
<nav class="legal__nav" aria-label="Documenti legali">{nav}</nav>
{body.strip()}
</main>
<footer class="footer">
  <div class="footer__inner">
    <p>Ressy è un progetto indipendente e open source con licenza MIT. <a href="https://github.com/quervv/ressy">Codice su GitHub</a>.</p>
    <p class="footer__links"><a href="/privacy">Privacy</a><a href="/cookie">Cookie</a><a href="/termini">Termini d’uso</a><button type="button" class="linklike" data-cookie-settings>Preferenze cookie</button></p>
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

for slug, title, desc, body in [
    ("privacy", "Privacy", "Come Ressy e il sito ressy.top trattano i dati: niente account, niente profilazione, le chiavi restano sul tuo PC.", PRIVACY),
    ("cookie", "Cookie", "I cookie e i dati che il sito ressy.top salva nel browser, e come cambiare il consenso.", COOKIE),
    ("termini", "Termini d’uso", "Le condizioni d’uso di Ressy, l’assistente vocale open source per Windows con licenza MIT.", TERMS),
]:
    (HERE / f"{slug}.html").write_text(page(slug, title, desc, body), encoding="utf-8")
print("ok")
