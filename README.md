# Ressy

Ressy è un assistente vocale AI per **Windows, macOS e Linux**. Tieni premuto **K**, di' **«Ressy, sveglia!»** e Ressy ti saluta. Poi apre programmi, gestisce finestre in multitasking, scrive su Discord, edita video su **CapCut** e **DaVinci Resolve**, cerca sul web, fa screenshot, imposta promemoria/timer e ti risponde a voce. Quando sei fuori casa la comandi da **Telegram** o da **Discord**, con messaggi scritti o vocali, attraverso **il tuo bot**.

- Sito: https://ressy.top
- Licenza: MIT, gratis e open source.
- Intelligenza: Groq, Gemini, OpenRouter (modelli gratuiti) o Claude, con la **tua** chiave API. Puoi inserirne più di una: se la prima arriva al limite Ressy continua con le altre.
- Comandi semplici (apri app e siti, meteo, volume, musica, ora, promemoria, calcoli) eseguiti sul PC senza usare richieste AI.
- AI sul PC (facoltativa): un modello Qwen 2.5 (Apache 2.0, 491 MB o 1,1 GB) eseguito dal motore ufficiale llama.cpp, scaricato alla prima scelta in `%APPDATA%\Ressy`. Gratis, offline e senza chiave: può essere il cervello principale o l'ultima riserva quando tutte le chiavi sono al limite. Gira solo su 127.0.0.1 e si spegne dopo 10 minuti di inattività.
- Consumi: chiedi «quanto mi resta delle API?» o guarda Impostazioni › Intelligenza › Consumi delle chiavi.
- Lingue: italiano e inglese, per finestre, voce, risposte e frasi di risveglio («Ressy, wake up!»). Si sceglie nell'installer o in Impostazioni › Generale; quando la cambi Ressy si riavvia. Le risposte automatiche del bot (avvisi offline/online, aiuto) per ora restano in italiano.
- Più richieste in una frase («apri Discord, scrivi a Marco che arrivo e crea la cartella scuola»): Ressy le divide in passi e li fa uno alla volta, in ordine, aspettando che ognuno sia finito (per esempio che Discord sia davvero aperto) prima del successivo.
- Nessun bot condiviso: ognuno crea il proprio. Gira dentro Ressy sul PC, oppure su un tuo server (self-host).

```
ressy/
├── desktop/            l'app desktop (Windows, macOS, Linux — PySide6): tasto, microfono, HUD, strumenti, il tuo bot
│   ├── installer/      Ressy-Setup.exe (Windows, senza amministratore)
│   └── scripts/install.sh  installer rapido per macOS e Linux
├── server/             il server del bot (aiohttp + Telegram + Discord): dentro l'app o self-host
└── deploy/             Docker Compose + Caddy per un server su VPS
```

Il sito [ressy.top](https://ressy.top) ha un suo repository: [quervv/ressy-web](https://github.com/quervv/ressy-web).

## Come funziona

1. **Sul PC** Ressy resta nell'area di notifica, accanto all'orologio.
   - Un tocco veloce di K scrive la lettera come sempre.
   - Se lo tieni premuto (350 ms), K diventa push-to-talk.
   - Si apre la finestra di Ressy con il logo (cinque barre viola, le stesse della sua voce), le linee della sua voce e, sotto, le tue linee e quello che ha sentito.
   - Da sveglia ascolta finché le dici «grazie, è tutto» o «vai a dormire», oppure finché resti in silenzio per 90 secondi.
2. **Il cervello** è Groq. L'audio va a Groq con la tua chiave solo per essere trascritto (Whisper large v3, con i nomi delle tue app e dei tuoi contatti come suggerimento). Il modello sceglie lo strumento giusto e Ressy risponde con una voce neurale (in italiano Isabella, Elsa o Diego; in inglese Ava o Andrew). Se la voce neurale non va, usa la voce di Windows. Ressy sa:
   - aprire, chiudere, affiancare, fissare e passare tra i programmi in multitasking; scrivere in qualsiasi app (Blocco note, Word, chat) e premere tasti;
   - editare video con **CapCut** o **DaVinci Resolve**: chiede di caricare i video (drag-and-drop sul PC o percorso in chat) poi costruisce il montaggio con sfondo sfocato/neon, ritmi, effetti, transizioni, sottotitoli e frasi ad impatto;
   - creare, leggere, rinominare, zippare, cercare file e gestire liste/note (solo nella tua cartella utente);
   - leggere lo schermo e cliccare su una scritta (con OCR locale: Windows OCR, oppure Tesseract su macOS e Linux);
   - scrivere su Discord (e leggere la chat aperta o di un amico): cerca la chat, verifica titolo/OCR e invia;
   - meteo, siti (anche «apri time.is»), YouTube, ricerche multi-sito, musica, volume, screenshot, promemoria, timer/cronometri, spegnimento;
   - eseguire comandi PowerShell su Windows o bash/zsh su macOS e Linux quando nessun altro strumento basta (i comandi distruttivi vengono rifiutati).
   
   Se si blocca mentre usa lo schermo, fa uno screenshot di dove si è fermata: in chat te lo manda, sul PC lo salva in `Immagini\Ressy`.
3. **Da remoto** scrivi al **tuo** bot Telegram o Discord. Tre modi, che scegli nell'installer o in Impostazioni › Da remoto:

   | Modo | Dove gira il bot | Se il PC è spento |
   |---|---|---|
   | Nessuno | — | — |
   | **Il tuo bot, su questo PC** | dentro Ressy | il bot tace; alla riaccensione ti scrive che è di nuovo online e **non** esegue i messaggi arrivati nel frattempo |
   | **Il tuo server (self-host)** | Ressy Server su un PC sempre acceso, o Docker su un VPS | il bot ti avvisa che il PC è offline e non esegue il comando |

4. **In ogni caso** un comando non viene mai eseguito in ritardo. Se chiudi Ressy, l'avviso arriva subito. Con un server, se il PC perde la rete il bot aspetta 45 secondi prima di avvisarti; quando il PC torna online, il bot ti scrive.

Perché un bot a testa: un bot unico per tutti sarebbe un punto unico da cui passano i comandi di tutti i PC; se si ferma, si fermano tutti. Con il tuo bot ogni Ressy è indipendente.

**Un bot, una persona.** Il primo account che collega un PC diventa il proprietario del bot (separatamente su Telegram e su Discord). Se poi un altro account scrive al bot, anche con un codice valido, viene bloccato per sempre: Ressy cancella la chat con lui (su Telegram anche i suoi messaggi, entro 48 ore; su Discord i messaggi del bot) e scrive al proprietario chi ci ha provato. Se il proprietario si scollega con `scollega`, il prossimo account che si collega diventa il nuovo proprietario.

## Installare (utenti)

### Windows
1. Scarica **`Ressy-Setup.exe`** dalle [release](https://github.com/quervv/ressy/releases/latest) e aprilo. Si installa in `%LOCALAPPDATA%\Programs\Ressy`, solo per il tuo utente, senza permessi da amministratore.
   - L'app non è firmata digitalmente: se compare «Windows ha protetto il PC», scegli «Ulteriori informazioni» → «Esegui comunque».
   - Nell'installer scegli cosa installare (Ressy, Ressy Server o entrambi), la cartella, il collegamento sul desktop e l'avvio con Windows.
   - Poi scegli come raggiungere Ressy da Telegram/Discord (vedi sopra) e incolli il token del tuo bot.
   - C'è anche una versione portatile, `Ressy-win64.zip`: estraila e avvia `Ressy\Ressy.exe`.

### macOS e Linux
1. Scarica **`Ressy-unix.tar.gz`** (o l'archivio nativo per il tuo OS nelle [release](https://github.com/quervv/ressy/releases/latest)), estrailo e avvia:
   ```bash
   ./desktop/scripts/install.sh
   ```
   Crea il venv, installa le dipendenze, aggiunge il comando `ressy` in `~/.local/bin` e crea `~/Applications/Ressy.app` (macOS) o il lanciatore desktop (Linux). Su Linux per l'audio di fallback installa `espeak-ng` e per il controllo finestre X11 `wmctrl`/`xdotool`/`xclip`. Su macOS consenti microfono e Accessibilità nelle Impostazioni di Sistema.
2. Al primo avvio si aprono le impostazioni.
   - Scegli l'AI sul PC oppure incolla la tua chiave Groq, Gemini, OpenRouter o Claude.
   - Le chiavi restano sul PC (`%APPDATA%\Ressy` su Windows cifrato con DPAPI, `~/.config/Ressy` su Linux e `~/Library/Application Support/Ressy` su macOS con permessi utente `0600`).
3. Tieni premuto K e di' «Ressy, sveglia!». Basta anche solo «Ressy» o «sveglia», e puoi aggiungere subito un comando: «Ressy, sveglia, apri Spotify». Il microfono parte appena premi K, così l'inizio della parola non si perde.
   - Nella pagina **Tasto e ascolto** puoi scegliere un altro tasto e la durata della pressione.
   - Tenendolo premuto, nella finestra aperta la lettera compare al massimo una volta. Se ti dà fastidio, scegli un tasto che non scrive, come F8.
4. Si disinstalla da Impostazioni di Windows › App (o dal menu Start › Ressy › Disinstalla Ressy). Puoi scegliere se tenere impostazioni e chiavi.

### Creare il tuo bot

- **Telegram:** scrivi a [@BotFather](https://t.me/BotFather) `/newbot`, scegli nome e username e copia il token (`123456789:AA…`). Facoltativo: `/setcommands` con `collega`, `stato`, `voce`, `notifiche`, `scollega`, `aiuto`.
- **Discord** (facoltativo):
  1. Nel [Developer Portal](https://discord.com/developers/applications) crea un'applicazione.
  2. In **Bot**, premi *Reset Token* e copia il token. Non serve nessun intent privilegiato: il bot legge solo i messaggi diretti.
  3. Invita il bot con un link da **OAuth2 → URL Generator**, scope `bot`, e scrivigli in privato.

### Collegare Telegram o Discord

1. Clicca l'icona di Ressy accanto all'orologio → **Collega Telegram o Discord…**.
2. Collega l'account:
   - **Telegram:** inquadra il QR con il telefono (oppure apri il link). Il bot ti collega da solo.
   - **Discord:** scrivi al bot in privato `!collega CODICE`.
3. Il codice è di 6 caratteri, vale una sola volta e scade dopo 10 minuti. Anche se qualcuno trova il tuo bot, senza codice non comanda niente.

Comandi del bot. Su Telegram si scrivono con `/`, su Discord con `!`:

| Comando | Cosa fa |
|---|---|
| `collega CODICE` | collega l'account al tuo PC |
| `stato` | stato del PC e delle preferenze |
| `voce sempre \| auto \| mai` | quando rispondere anche con un vocale |
| `notifiche on \| off` | avvisi quando il PC va offline o torna online |
| `scollega` | scollega l'account |
| `aiuto` | l'elenco dei comandi |

Tutto il resto è un comando per Ressy, scritto o a voce. Esempi: «apri Spotify», «scrivi su Discord a Marco che arrivo tra dieci minuti», «fammi uno screenshot».

### Privacy

- I registri restano sul PC (`%APPDATA%\Ressy\logs`), non contengono il testo di quello che dici o scrivi e nascondono chiavi e token.
- Meteo: Open-Meteo (gratuito, senza account). Se in Impostazioni › Generale non scrivi una città, la posizione approssimativa del PC si ricava una volta a settimana dall'indirizzo IP (ipapi.co).
- La lettura dello schermo usa il riconoscimento del testo di Windows: le immagini non lasciano il PC.
- Con il modello vocale sul PC la tua voce non lascia il PC: viene trascritta lì e al provider scelto (Groq, Gemini, OpenRouter o Claude) arriva solo il testo. Il modello si scarica una volta in `%APPDATA%\Ressy\models`.
- Non c'è un server centrale: i messaggi vanno da Telegram/Discord al tuo bot, che gira da te, e da lì al tuo PC. Il bot non salva il testo dei messaggi.
- Solo gli account che colleghi tu possono comandare il PC. Ogni comando da remoto compare anche come notifica sul PC; puoi spegnere la notifica nelle impostazioni, alla voce **Da remoto**. Dalla stessa pagina vedi gli account collegati e li scolleghi.

## Ressy Server (self-host)

Serve se vuoi che il bot giri giorno e notte e ti avvisi quando un PC va offline, o se hai più PC con un solo bot.

### Su un PC Windows sempre acceso

1. Apri `Ressy-Setup.exe` e spunta **Ressy Server**. Incolla il token del bot e scegli la porta (8765).
2. Il server parte con Windows, senza finestre (`Ressy.exe --server`; si ferma con *Ferma Ressy Server* nel menu Start). Registri in `%APPDATA%\Ressy\logs\server.log`.
3. Se Windows chiede di consentire l'accesso alla rete, consenti le reti private.
4. Sugli altri PC: Ressy › Impostazioni › Da remoto › **Il tuo server**, indirizzo `ws://IP-DEL-SERVER:8765/ws/agent`. Il PC dove gira il server si collega da solo.

`ws://` non è cifrato: va bene nella rete di casa (o con una VPN come Tailscale). Per Internet usa un VPS con HTTPS (sotto).

### Su un VPS con Docker

Ti servono un VPS con Docker e un dominio che punta al VPS. Caddy ottiene da solo i certificati HTTPS.

```bash
cp server/.env.example server/.env   # compila TELEGRAM_BOT_TOKEN, DISCORD_BOT_TOKEN, DISCORD_INVITE_URL, RESSY_PUBLIC_URL
# in deploy/Caddyfile sostituisci ressy.top con il tuo dominio
cd deploy
docker compose up -d --build
```

Caddy inoltra `/ws/agent` (la connessione delle app) e `/health` al server, e, se cloni [ressy-web](https://github.com/quervv/ressy-web) nella cartella `web/`, serve anche il sito. Il database SQLite vive nel volume `ressy-data`. Il file `server/.env.example` spiega ogni variabile: tolleranza offline, timeout dei comandi, limite di comandi al minuto. Nelle app scrivi `wss://tuodominio/ws/agent`.

### Senza Docker

```bash
cd server
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m ressy_server        # legge .env dalla cartella corrente
.venv/bin/python -m pytest -q tests     # test (requirements-dev.txt)
```

## Sviluppo dell'app desktop

Requisiti: Windows 10/11, macOS o Linux (Python 3.10–3.12).

```powershell
cd desktop
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt -r requirements-dev.txt
.venv\Scripts\python -m ressy            # avvia l'app (il bot "su questo PC" usa ..\server)
.venv\Scripts\python -m pytest -q tests  # test
.venv\Scripts\python installer\setup_app.py ..\web\download\Ressy-win64.zip   # prova l'installer
```

Per pubblicare una versione:

```powershell
.venv\Scripts\python scripts\build_release.py     # web\download\Ressy-Setup.exe, Ressy-win64.zip, Ressy-unix.tar.gz, Ressy-source.zip
.venv\Scripts\python scripts\build_web_assets.py  # favicon, icone e immagine di condivisione del sito
```

I download del sito puntano alle [Release su GitHub](https://github.com/quervv/ressy/releases): carica lì i file creati da `build_release.py`.

Le impostazioni stanno in `%APPDATA%\Ressy\config.json` su Windows, `~/Library/Application Support/Ressy/config.json` su macOS e `~/.config/Ressy/config.json` su Linux (quelle del server in `server.json`).

## Licenza

MIT: vedi [LICENSE](LICENSE). Ressy è un progetto indipendente e non è affiliato a Telegram, Discord, Groq, Google, OpenRouter, Anthropic o Microsoft. Il font Archivo è distribuito con licenza SIL Open Font License (`fonts/OFL.txt`).
