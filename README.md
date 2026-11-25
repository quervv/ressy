# Ressy

Ressy è un assistente vocale per Windows. Tieni premuto **K**, di' **«Ressy, sveglia!»** e Ressy ti saluta. Poi apre programmi, scrive su Discord, cerca sul web, fa screenshot, imposta promemoria e ti risponde a voce. Quando sei fuori casa la comandi da **Telegram** o da **Discord**, con messaggi scritti o vocali, attraverso **il tuo bot**.

- Sito: https://ressy.top
- Licenza: MIT, gratis e open source.
- Intelligenza: Groq, Gemini, OpenRouter (modelli gratuiti) o Claude, con la **tua** chiave API. Puoi inserirne più di una: se la prima arriva al limite Ressy continua con le altre.
- Comandi semplici (apri app e siti, meteo, volume, musica, ora) eseguiti sul PC senza usare richieste AI.
- Consumi: chiedi «quanto mi resta delle API?» o guarda Impostazioni › Intelligenza › Consumi delle chiavi.
- Nessun bot condiviso: ognuno crea il proprio. Gira dentro Ressy sul PC, oppure su un tuo server (self-host).

```
ressy/
├── desktop/            l'app Windows (PySide6): tasto, microfono, HUD, strumenti, il tuo bot
│   └── installer/      Ressy-Setup.exe (installazione per l'utente, senza amministratore)
├── server/             il server del bot (aiohttp + Telegram + Discord): dentro l'app o self-host
├── deploy/             Docker Compose + Caddy per un server su VPS (e il sito)
└── web/                la landing page statica di ressy.top
```

## Come funziona

1. **Sul PC** Ressy resta nell'area di notifica, accanto all'orologio.
   - Un tocco veloce di K scrive la lettera come sempre.
   - Se lo tieni premuto (350 ms), K diventa push-to-talk.
   - Si apre la finestra di Ressy con il logo (cinque barre viola, le stesse della sua voce), le linee della sua voce e, sotto, le tue linee e quello che ha sentito.
   - Da sveglia ascolta finché le dici «grazie, è tutto» o «vai a dormire», oppure finché resti in silenzio per 90 secondi.
2. **Il cervello** è Groq. L'audio va a Groq con la tua chiave solo per essere trascritto (Whisper large v3, con i nomi delle tue app e dei tuoi contatti come suggerimento). Il modello sceglie lo strumento giusto e Ressy risponde con una voce neurale italiana (Isabella, Elsa o Diego). Se la voce neurale non va, usa la voce di Windows. Ressy sa:
   - aprire, chiudere e passare tra i programmi; scrivere in qualsiasi app (Blocco note, Word, chat) e premere tasti;
   - creare, leggere e aggiungere testo ai file e creare cartelle (solo nella tua cartella utente);
   - leggere lo schermo e cliccare su una scritta (con il riconoscimento del testo di Windows, sul PC);
   - scrivere su Discord: cerca la chat, legge i risultati sullo schermo, clicca quella giusta e controlla l'intestazione prima di scrivere;
   - meteo, siti (anche «apri time.is»), YouTube, ricerche, musica, volume, screenshot, promemoria, spegnimento;
   - eseguire comandi PowerShell quando nessun altro strumento basta (i comandi distruttivi vengono rifiutati).
   
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

1. Scarica **`Ressy-Setup.exe`** da https://ressy.top e aprilo. Si installa in `%LOCALAPPDATA%\Programs\Ressy`, solo per il tuo utente, senza permessi da amministratore.
   - L'app non è firmata digitalmente: se compare «Windows ha protetto il PC», scegli «Ulteriori informazioni» → «Esegui comunque».
   - Nell'installer scegli cosa installare (Ressy, Ressy Server o entrambi), la cartella, il collegamento sul desktop e l'avvio con Windows.
   - Poi scegli come raggiungere Ressy da Telegram/Discord (vedi sopra) e incolli il token del tuo bot.
   - C'è anche una versione portatile, `Ressy-win64.zip`: estraila e avvia `Ressy\Ressy.exe`.
2. Al primo avvio si aprono le impostazioni.
   - Crea una chiave su https://console.groq.com/keys e incollala nella pagina **Groq**: Ressy la verifica.
   - Chiave Groq e token dei bot restano sul PC, cifrati con Windows (DPAPI).
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

Caddy inoltra `/ws/agent` (la connessione delle app) e `/health` al server, e serve anche il sito da `web/`. Il database SQLite vive nel volume `ressy-data`. Il file `server/.env.example` spiega ogni variabile: tolleranza offline, timeout dei comandi, limite di comandi al minuto. Nelle app scrivi `wss://tuodominio/ws/agent`.

### Senza Docker

```bash
cd server
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m ressy_server        # legge .env dalla cartella corrente
.venv/bin/python -m pytest -q tests     # test (requirements-dev.txt)
```

## Sviluppo dell'app desktop

Requisiti: Windows 10/11 a 64 bit, Python 3.12 (la versione con cui è testata).

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
.venv\Scripts\python scripts\build_release.py     # web\download\Ressy-Setup.exe, Ressy-win64.zip, Ressy-source.zip
.venv\Scripts\python scripts\build_web_assets.py  # favicon, icone e immagine di condivisione del sito
```

I download del sito puntano alle [Release su GitHub](https://github.com/quervv/ressy/releases): carica lì i file creati da `build_release.py`.

Le impostazioni stanno in `%APPDATA%\Ressy\config.json` (quelle del server in `server.json`).

## Licenza

MIT: vedi [LICENSE](LICENSE). Ressy è un progetto indipendente e non è affiliato a Telegram, Discord, Groq, Google, OpenRouter, Anthropic o Microsoft. Il font Archivo è distribuito con licenza SIL Open Font License (`fonts/OFL.txt`).
