EN: dict[str, str] = {
    "Ressy, l'assistente vocale per Windows.":
        'Ressy, the voice assistant for Windows.',
    "L'area di notifica di Windows non è disponibile: Ressy non può partire.":
        'The Windows notification area is not available: Ressy cannot start.',
    'Ressy aggiornata':
        'Ressy updated',
    'Ressy è pronta':
        'Ressy is ready',
    'Aggiorna Ressy alla versione {version}…':
        'Update Ressy to version {version}…',
    'Ora hai la versione {version}.':
        'You now have version {version}.',
    "Benvenuto! Per iniziare scegli l'intelligenza di Ressy (Groq, Gemini, OpenRouter o Claude) e incolla la chiave. Poi tieni premuto {hotkey_name} e di' «Ressy, sveglia!».":
        "Welcome! To get started, choose Ressy's brain (Groq, Gemini, OpenRouter or Claude) and paste the key. Then hold {hotkey_name} and say «Ressy, wake up!».",
    "Tieni premuto {hotkey_name} e di' «Ressy, sveglia!»":
        'Hold {hotkey_name} and say «Ressy, wake up!»',
    'Impossibile avviare il microfono: {exc}':
        'Cannot start the microphone: {exc}',
    'Impossibile aprire il microfono: {exc}':
        'Cannot open the microphone: {exc}',
    'Non rifare le azioni già fatte e non anticipare le prossime. Alla fine rispondi con una frase breve su cosa hai fatto.':
        "Don't redo the actions already done and don't do the next ones ahead of time. At the end, answer with a short sentence about what you did.",
    'Fatto.':
        'Done.',
    'Non ho una risposta per questo.':
        "I don't have an answer for that.",
    "Non eseguito: l'azione prima non è riuscita. Se serve ancora, richiedila.":
        'Not run: the previous action failed. If it is still needed, ask for it again.',
    'La richiesta ha {total} azioni: le fai una alla volta, in ordine.':
        'The request has {total} actions: do them one at a time, in order.',
    "Ora fai solo l'azione {index}: {step}":
        'Now do only action {index}: {step}',
    'Già fatto:':
        'Already done:',
    'Non ho fatto {steps}, perché serviva il passo prima.':
        "I didn't do {steps}, because it needed the step before.",
    'Poi devo ancora: {steps}.':
        'I still have to: {steps}.',
    'Già fatto poco fa: ':
        'Already done a moment ago: ',
    'fatto':
        'done',
    'non riuscito: ':
        'failed: ',
    '«{step}» non è riuscito.':
        "«{step}» didn't work.",
    'Trascrizione non disponibile.':
        'Transcription not available.',
    'Manca la chiave API di {NAME}: inseriscila nelle impostazioni di Ressy.':
        "The {NAME} API key is missing: add it in Ressy's settings.",
    'La chiave API di {name} non è valida.':
        'The {name} API key is not valid.',
    'Errore {name} {status}':
        '{name} error {status}',
    'Ho raggiunto il limite di richieste del tuo account {NAME}: riprova tra un minuto.':
        'I reached the request limit of your {NAME} account: try again in a minute.',
    'Nessun modello {NAME} disponibile.':
        'No {NAME} model available.',
    'Accesso negato da {name}.':
        'Access denied by {name}.',
    '{NAME} non risponde (timeout).':
        '{NAME} is not responding (timeout).',
    'Non riesco a contattare {NAME}: controlla la connessione.':
        "I can't reach {NAME}: check the connection.",
    "Questo con l'AI sul PC non riesco a farlo. Con una chiave online (Groq o Gemini, gratis) sì.":
        "I can't do this with the AI on the PC. With an online key (Groq or Gemini, free) I can.",
    'il motore AI scaricato non corrisponde a quello ufficiale':
        "the downloaded AI engine doesn't match the official one",
    "llama-server.exe non trovato nell'archivio":
        'llama-server.exe not found in the archive',
    'Il modello sul PC non può cercare sul web.':
        "The model on the PC can't search the web.",
    'Non ci sono riuscita: ':
        "I didn't manage: ",
    'Il motore AI sul PC non è partito in tempo.':
        "The AI engine on the PC didn't start in time.",
    'Il modello AI sul PC non è ancora scaricato (Impostazioni › Intelligenza).':
        "The AI model on the PC isn't downloaded yet (Settings › Brain).",
    'Il modello AI sul PC non è riuscito a rispondere.':
        "The AI model on the PC couldn't answer.",
    'errore sconosciuto':
        'unknown error',
    'Il motore AI sul PC ha risposto {status}.':
        'The AI engine on the PC answered {status}.',
    'Risultato di ':
        'Result of ',
    "Il motore AI sul PC si è chiuso all'avvio (codice {code}).":
        'The AI engine on the PC closed while starting (code {code}).',
    'Manca la chiave API di Gemini.':
        'The Gemini API key is missing.',
    'OpenRouter non ha modelli gratuiti disponibili adesso.':
        'OpenRouter has no free models available right now.',
    'Manca la chiave API di Claude.':
        'The Claude API key is missing.',
    'La chiave API di Claude non è valida.':
        'The Claude API key is not valid.',
    'Ho raggiunto il limite di richieste del tuo account Claude: riprova tra un minuto.':
        'I reached the request limit of your Claude account: try again in a minute.',
    'Non riesco a contattare Claude: controlla la connessione.':
        "I can't reach Claude: check the connection.",
    ' Per non fermarti mai aggiungi una seconda chiave gratuita (Gemini o OpenRouter) nelle impostazioni.':
        ' To never stop, add a second free key (Gemini or OpenRouter) in the settings.',
    'Nessun servizio di ricerca disponibile.':
        'No search service available.',
    'Gemini non risponde (timeout).':
        'Gemini is not responding (timeout).',
    'Non riesco a contattare Gemini.':
        "I can't reach Gemini.",
    ' Nomi che potrebbero comparire: {prompt}':
        ' Names that may come up: {prompt}',
    'Errore Claude: {name}':
        'Claude error: {name}',
    'Errore Claude {status_code}: {message}':
        'Claude error {status_code}: {message}',
    'Mi dispiace, con questo non posso aiutarti.':
        "I'm sorry, I can't help with that.",
    'Ho raggiunto il limite di richieste del tuo account {first}: riprova tra un minuto.{hint}':
        'I reached the request limit of your {first} account: try again in a minute.{hint}',
    'Non si può dividere per zero.':
        "You can't divide by zero.",
    'AI sul PC':
        'AI on the PC',
    'tra {round} ore':
        'in {round} hours',
    'Non hai ancora inserito chiavi API.':
        "You haven't entered any API keys yet.",
    'tra {max} secondi':
        'in {max} seconds',
    'tra {round} minuti':
        'in {round} minutes',
    'Oggi Ressy ha fatto {fmt} richiesta a {name}':
        'Today Ressy made {fmt} request to {name}',
    'Oggi Ressy ha fatto {fmt} richieste a {name}':
        'Today Ressy made {fmt} requests to {name}',
    'Nessun limite, gratis e offline.':
        'No limits, free and offline.',
    'Token in entrata':
        'Input tokens',
    'Token in uscita':
        'Output tokens',
    'Token':
        'Tokens',
    'Account gratuito: 20 richieste al minuto sui modelli gratis.':
        'Free account: 20 requests per minute on the free models.',
    'Adesso è al limite: torna disponibile {when}.':
        "It's at the limit right now: available again {when}.",
    '{name} non comunica quanto resta: i limiti esatti sono su {value}.':
        "{name} doesn't report how much is left: the exact limits are on {value}.",
    'Nessun dato ancora: lo saprò dopo la prima richiesta a {name}.':
        "No data yet: I'll know after the first request to {name}.",
    'Richieste gratuite oggi: ne restano {fmt} su {fmt2}.':
        'Free requests today: {fmt} left out of {fmt2}.',
    'Credito della chiave: {value:.2f} $ su {value2:.2f} $.':
        'Key credit: $ {value:.2f} left out of $ {value2:.2f}.',
    'Oggi ha risposto {fmt} volte.':
        'Today it answered {fmt} times.',
    'Richieste oggi: ne restano {fmt} su {fmt2} (modello {value}).':
        'Requests today: {fmt} left out of {fmt2} (model {value}).',
    'Richieste al minuto: ne restano {fmt} su {fmt2}.':
        'Requests per minute: {fmt} left out of {fmt2}.',
    ' ({fmt} token).':
        ' ({fmt} tokens).',
    ' (si è già ricaricato)':
        ' (already refilled)',
    '{label} al minuto: {fmt} su {fmt2}.':
        '{label} per minute: {fmt} out of {fmt2}.',
    'Token al minuto: {fmt} su {fmt2}':
        'Tokens per minute: {fmt} out of {fmt2}',
    'Isabella (italiano, femminile)':
        'Isabella (Italian, female)',
    'Elsa (italiano, femminile)':
        'Elsa (Italian, female)',
    'Diego (italiano, maschile)':
        'Diego (Italian, male)',
    'Giuseppe (italiano, maschile)':
        'Giuseppe (Italian, male)',
    'Ava (inglese, femminile)':
        'Ava (English, female)',
    'Andrew (inglese, maschile)':
        'Andrew (English, male)',
    'Sul PC':
        'On the PC',
    'Claude Opus 5.5 (il più capace)':
        'Claude Opus 5.5 (the most capable)',
    'Claude Haiku 5.5 (il più veloce ed economico)':
        'Claude Haiku 5.5 (the fastest and cheapest)',
    'Leggero':
        'Light',
    'Bilanciato':
        'Balanced',
    'Preciso':
        'Accurate',
    'Leggera':
        'Light',
    'Consigliata':
        'Recommended',
    'Scarica il modello AI sul PC (Impostazioni › Intelligenza) o inserisci una chiave API.':
        'Download the AI model to the PC (Settings › Brain) or enter an API key.',
    'Scarica il modello vocale sul PC (Impostazioni › Voce) o scegli di capire la voce online.':
        'Download the speech model to the PC (Settings › Voice) or choose to understand speech online.',
    'Per usare Ressy inserisci la chiave API di {value} (Impostazioni › Intelligenza).':
        'To use Ressy, enter the {value} API key (Settings › Brain).',
    'Per capire la voce con {value} serve la sua chiave API, oppure scegli il modello sul PC.':
        'To understand speech with {value} you need its API key, or choose the model on the PC.',
    'Apro il programma…':
        'Opening the program…',
    'Chiudo il programma…':
        'Closing the program…',
    'Guardo le finestre aperte…':
        'Looking at the open windows…',
    'Cambio finestra…':
        'Switching window…',
    'Scrivo su Discord…':
        'Writing on Discord…',
    'Apro il browser…':
        'Opening the browser…',
    'Cerco su Google…':
        'Searching on Google…',
    'Cerco su YouTube…':
        'Searching on YouTube…',
    'Cerco sul web…':
        'Searching the web…',
    'Controllo la musica…':
        'Controlling the music…',
    'Regolo il volume…':
        'Adjusting the volume…',
    'Faccio uno screenshot…':
        'Taking a screenshot…',
    'Gestisco l’alimentazione…':
        'Managing power…',
    'Controllo il PC…':
        'Checking the PC…',
    'Apro la cartella…':
        'Opening the folder…',
    'Scrivo…':
        'Typing…',
    'Premo i tasti…':
        'Pressing keys…',
    'Copio negli appunti…':
        'Copying to the clipboard…',
    'Gestisco i promemoria…':
        'Managing reminders…',
    'Creo il file…':
        'Creating the file…',
    'Creo la cartella…':
        'Creating the folder…',
    'Sistemo i file…':
        'Sorting out the files…',
    'Aspetto…':
        'Waiting…',
    'Leggo il file…':
        'Reading the file…',
    'Guardo nella cartella…':
        'Looking in the folder…',
    'Scrivo nell’app…':
        'Writing in the app…',
    'Guardo lo schermo…':
        'Looking at the screen…',
    'Clicco…':
        'Clicking…',
    'Guardo il meteo…':
        'Checking the weather…',
    'Eseguo un comando…':
        'Running a command…',
    'Si è verificato un errore imprevisto.':
        'An unexpected error occurred.',
    'Ci sto mettendo troppo: riprova tra poco.':
        'This is taking too long: try again shortly.',
    ' (in ritardo: il PC era spento o in sospensione)':
        ' (late: the PC was off or asleep)',
    'Promemoria':
        'Reminder',
    'La chiave API di {name} manca o non è valida: controllala nelle impostazioni di Ressy.':
        "The {name} API key is missing or not valid: check it in Ressy's settings.",
    'Non riesco a raggiungere {name}: controlla la connessione a internet.':
        "I can't reach {name}: check the internet connection.",
    '{name} ha restituito un errore, riprova tra poco.':
        '{name} returned an error, try again shortly.',
    'Microfono':
        'Microphone',
    'Il messaggio è vuoto.':
        'The message is empty.',
    'Promemoria: {text}':
        'Reminder: {text}',
    'Non riesco a intercettare la tastiera: il tasto per parlare non funzionerà.':
        "I can't listen to the keyboard: the talk key won't work.",
    'Microfono non disponibile':
        'Microphone not available',
    'Non ho sentito niente.':
        "I didn't hear anything.",
    'Ciao! Per iniziare mi serve una chiave API: inseriscila nelle impostazioni.':
        'Hi! To get started I need an API key: add it in the settings.',
    'Sul PC manca una chiave API: ':
        'An API key is missing on the PC: ',
    'Non sono riuscita a capire il messaggio vocale.':
        "I couldn't understand the voice message.",
    'Il microfono predefinito di Windows non manda suono: uso «{name}».':
        "The Windows default microphone sends no sound: I'm using «{name}».",
    'Non ho capito bene: tieni premuto K e riprova «Ressy, sveglia!».':
        "I didn't quite get that: hold K and try «Ressy, wake up!» again.",
    'Il messaggio vocale è arrivato danneggiato.':
        'The voice message arrived damaged.',
    'Comando da {label}{who}':
        'Command from {label}{who}',
    'Comando da {label}…':
        'Command from {label}…',
    'Ressy collegata':
        'Ressy connected',
    'Il server non ha risposto.':
        "The server didn't answer.",
    'Non riesco a scollegare: {exc}':
        "I can't unlink: {exc}",
    'Il bot non è partito ({name}).':
        "The bot didn't start ({name}).",
    "Per svegliarmi di' «{capitalize}!»":
        'To wake me up, say «{capitalize}!»',
    'Ora puoi comandare questo PC da {platform} ({get}).':
        'You can now control this PC from {platform} ({get}).',
    'Non connessa al server.':
        'Not connected to the server.',
    'Ressy non è connessa al server: controlla la connessione.':
        'Ressy is not connected to the server: check the connection.',
    'Errore interno di Ressy sul PC.':
        'Internal Ressy error on the PC.',
    'nuovo tentativo tra {seconds} s':
        'retrying in {seconds} s',
    'Ressy si è collegata al server da un altro PC con la stessa identità.':
        'Ressy connected to the server from another PC with the same identity.',
    'Connessione al server persa.':
        'Connection to the server lost.',
    'Identità del PC non valida.':
        'Invalid PC identity.',
    'Il token del bot non è valido: copialo di nuovo da BotFather o dal Discord Developer Portal.':
        'The bot token is not valid: copy it again from BotFather or from the Discord Developer Portal.',
    'Non riesco a raggiungere Telegram o Discord: controlla la connessione.':
        "I can't reach Telegram or Discord: check the connection.",
    'Il bot si è fermato ({name}).':
        'The bot stopped ({name}).',
    'Manca il token del bot.':
        'The bot token is missing.',
    'Il bot non è partito in tempo.':
        "The bot didn't start in time.",
    'libopus non disponibile':
        'libopus not available',
    'non è una nota vocale Opus':
        "it's not an Opus voice note",
    'non è un file Ogg':
        "it's not an Ogg file",
    'Il modello vocale sul PC non è ancora scaricato: scaricalo in Impostazioni › Voce.':
        "The speech model on the PC isn't downloaded yet: download it in Settings › Voice.",
    "Il modello vocale sul PC non è riuscito a capire l'audio, riprova.":
        "The speech model on the PC couldn't understand the audio, try again.",
    'Non riesco a leggere questo audio sul PC: manda una nota vocale normale o scegli di capire la voce online.':
        "I can't read this audio on the PC: send a normal voice note or choose to understand speech online.",
    'Dopo la risposta torno a dormire.':
        "After the answer I'll go back to sleep.",
    'Non ho dati sui consumi.':
        'I have no usage data.',
    'Non ci sono finestre aperte.':
        'There are no open windows.',
    'Finestre aperte:\n':
        'Open windows:\n',
    'Windows non mi ha permesso di portare la finestra in primo piano.':
        "Windows didn't let me bring the window to the front.",
    'Ho chiuso {name} forzatamente.':
        'I force-closed {name}.',
    'Il PC è bloccato: non posso cambiare finestra finché non viene sbloccato.':
        "The PC is locked: I can't switch windows until it's unlocked.",
    "Ho avviato {name}, ma la sua finestra non si vede ancora (forse è nell'area di notifica).":
        "I started {name}, but its window isn't showing yet (maybe it's in the notification area).",
    'Ho avviato {name}.':
        'I started {name}.',
    "Non trovo nessun programma chiamato '{name}' nel menu Start.":
        "I can't find any program called '{name}' in the Start menu.",
    'Ho chiuso {name}.':
        'I closed {name}.',
    'Ho portato in primo piano {value}.':
        'I brought {value} to the front.',
    'Ho avviato {name}: il gioco si apre tra poco.':
        'I started {name}: the game opens shortly.',
    'Ho aperto {name}: è pronto.':
        "I opened {name}: it's ready.",
    "Non ho trovato '{name}' con certezza. Forse intendevi: {names}?":
        "I couldn't find '{name}' for sure. Did you mean: {names}?",
    "Non vedo finestre aperte di '{name}'.":
        "I don't see any open windows of '{name}'.",
    'Ho chiesto a {name} di chiudersi, ma {len} finestra/e è ancora aperta (forse chiede di salvare). Posso forzare la chiusura se vuoi, perdendo le modifiche non salvate.':
        "I asked {name} to close, but {len} window(s) are still open (maybe it's asking to save). I can force it to close if you want, losing unsaved changes.",
    'Ho chiuso le finestre di {name}; il programma resta attivo in background (area di notifica).':
        'I closed the windows of {name}; the program keeps running in the background (notification area).',
    'Non sono riuscita a chiudere {name} (permessi insufficienti?).':
        "I couldn't close {name} (not enough permissions?).",
    'Discord non sembra installato su questo PC.':
        "Discord doesn't seem to be installed on this PC.",
    " Chiedi all'utente di ripetere o scrivere il nome come appare su Discord.":
        ' Ask the user to repeat or to write the name as it appears on Discord.',
    'A chi devo scrivere?':
        'Who should I write to?',
    'Il PC è bloccato: non posso scrivere su Discord finché non viene sbloccato.':
        "The PC is locked: I can't write on Discord until it's unlocked.",
    'Non riesco a portare Discord in primo piano.':
        "I can't bring Discord to the front.",
    'Discord ha perso il focus: messaggio NON inviato.':
        'Discord lost focus: message NOT sent.',
    'Discord ha perso il focus mentre scrivevo: controlla la chat, il messaggio potrebbe non essere partito.':
        'Discord lost focus while I was typing: check the chat, the message may not have been sent.',
    'la chat aperta':
        'the open chat',
    'Messaggio inviato su Discord a {target}.':
        'Message sent on Discord to {target}.',
    'Discord ha perso il focus mentre cercavo la chat: messaggio NON inviato.':
        'Discord lost focus while I was looking for the chat: message NOT sent.',
    " Nella ricerca di Discord ci sono: {join}. Chiedi all'utente se intendeva uno di questi e, se sì, riprova con quel nome esatto.":
        " Discord's search shows: {join}. Ask the user whether they meant one of these and, if so, try again with that exact name.",
    "Non ho trovato la chat con '{recipient}' su Discord (o non sono riuscita a verificarla): il messaggio NON è stato inviato.{hint}":
        "I couldn't find the chat with '{recipient}' on Discord (or couldn't verify it): the message was NOT sent.{hint}",
    'Discord non si è aperto in tempo. Riprova tra poco.':
        "Discord didn't open in time. Try again shortly.",
    'Il messaggio è troppo lungo per Discord ({len} caratteri, massimo {MAX_LENGTH}).':
        'The message is too long for Discord ({len} characters, maximum {MAX_LENGTH}).',
    'sereno':
        'clear sky',
    'quasi sereno':
        'mostly clear',
    'parzialmente nuvoloso':
        'partly cloudy',
    'nuvoloso':
        'cloudy',
    'nebbia':
        'fog',
    'nebbia con brina':
        'freezing fog',
    'pioviggine leggera':
        'light drizzle',
    'pioviggine':
        'drizzle',
    'pioviggine intensa':
        'heavy drizzle',
    'pioviggine gelata':
        'freezing drizzle',
    'pioggia leggera':
        'light rain',
    'pioggia':
        'rain',
    'pioggia forte':
        'heavy rain',
    'pioggia gelata':
        'freezing rain',
    'pioggia gelata forte':
        'heavy freezing rain',
    'neve leggera':
        'light snow',
    'neve':
        'snow',
    'neve forte':
        'heavy snow',
    'nevischio':
        'snow grains',
    'rovesci leggeri':
        'light showers',
    'rovesci':
        'showers',
    'rovesci violenti':
        'violent showers',
    'rovesci di neve':
        'snow showers',
    'forti rovesci di neve':
        'heavy snow showers',
    'temporale':
        'thunderstorm',
    'temporale con grandine':
        'thunderstorm with hail',
    'temporale con grandine forte':
        'thunderstorm with heavy hail',
    'Ho aggiunto il testo a {name} in {parent}.':
        'I added the text to {name} in {parent}.',
    'Ho creato {name} in {parent}.':
        'I created {name} in {parent}.',
    'sul Desktop':
        'on the Desktop',
    'Desktop':
        'Desktop',
    'in Documenti':
        'in Documents',
    'Documenti':
        'Documents',
    'in Download':
        'in Downloads',
    'Download':
        'Downloads',
    'in Immagini':
        'in Pictures',
    'Immagini':
        'Pictures',
    'in Musica':
        'in Music',
    'Musica':
        'Music',
    'in Video':
        'in Videos',
    'Video':
        'Videos',
    'la cartella':
        'the folder',
    'il file':
        'the file',
    'Non leggo testo sullo schermo.':
        "I can't read any text on the screen.",
    'Testo visibile (OCR, può contenere errori):\n':
        'Visible text (OCR, may contain errors):\n',
    'la tua zona':
        'your area',
    'oggi':
        'today',
    'domani':
        'tomorrow',
    '(nessun output)':
        '(no output)',
    'Manca il nome del file.':
        'The file name is missing.',
    'Il nome del file contiene caratteri non ammessi.':
        "The file name contains characters that aren't allowed.",
    'Per sicurezza creo e leggo file solo dentro la tua cartella utente.':
        'For safety I only create and read files inside your user folder.',
    'Non tocco i file di sistema delle app (AppData).':
        "I don't touch the apps' system files (AppData).",
    'Il contenuto è troppo lungo.':
        'The content is too long.',
    'La cartella {name} è stata creata {where}.':
        'The folder {name} was created {where}.',
    'È una delle cartelle principali del tuo utente: non la sposto e non la cancello.':
        "It's one of your user's main folders: I won't move or delete it.",
    'In quale cartella devo metterlo?':
        'Which folder should I put it in?',
    'Non posso metterlo dentro se stesso.':
        "I can't put it inside itself.",
    'Ho copiato {kind} {name} {where}.':
        'I copied {kind} {name}: the copy is {where}.',
    'Quanti secondi devo aspettare?':
        'How many seconds should I wait?',
    'Ho aspettato {seconds:g} secondi.':
        'I waited {seconds:g} seconds.',
    'Il file è troppo grande da leggere.':
        'The file is too big to read.',
    'Non è un file di testo.':
        "It's not a text file.",
    'Contenuto di {name}:\n{value}{more}':
        'Contents of {name}:\n{value}{more}',
    'Non è una cartella.':
        "It's not a folder.",
    'Testo troppo lungo.':
        'Text too long.',
    'Il PC è bloccato: non posso scrivere finché non viene sbloccato.':
        "The PC is locked: I can't type until it's unlocked.",
    'Il riconoscimento del testo di Windows non è disponibile.':
        'Windows text recognition is not available.',
    'Cosa devo cliccare?':
        'What should I click?',
    'Il PC è bloccato.':
        'The PC is locked.',
    'Ho cliccato su «{value}».':
        'I clicked «{value}».',
    'Non so dove sei: dimmi la città.':
        "I don't know where you are: tell me the city.",
    'Comando vuoto.':
        'Empty command.',
    'Comando troppo lungo.':
        'Command too long.',
    'Questo comando può danneggiare il PC o i dati: non lo eseguo. Fallo tu se sei sicuro.':
        "This command could damage the PC or your data: I won't run it. Do it yourself if you're sure.",
    'La cartella {name} esisteva già {where}.':
        'The folder {name} already existed {where}.',
    'Ho spostato {kind} {name} nel Cestino (si può ripristinare da lì).':
        'I moved {kind} {name} to the Recycle Bin (it can be restored from there).',
    'Dimmi il nuovo nome (senza caratteri come / : * ?).':
        'Tell me the new name (without characters like / : * ?).',
    'Ho rinominato {kind} {name} in {name2}.':
        'I renamed {kind} {name} to {name2}.',
    'Ho spostato {kind} {name} {where}.':
        "I moved {kind} {name}: it's now {where}.",
    '{app} è aperto e pronto.':
        '{app} is open and ready.',
    'Ho scritto il testo in «{value}».':
        'I wrote the text in «{value}».',
    'Ho scritto il testo in {app}.':
        'I wrote the text in {app}.',
    'Il servizio meteo non risponde, riprova tra poco.':
        "The weather service isn't responding, try again shortly.",
    'Meteo a {label} adesso: {sky}, {temp}°C (percepiti {feels}°C), umidità {humidity}%, vento {wind} km/h.':
        'Weather in {label} now: {sky}, {temp}°C (feels like {feels}°C), humidity {humidity}%, wind {wind} km/h.',
    '%d/%m':
        '%a %d',
    'Il comando ha impiegato più di 60 secondi ed è stato interrotto.':
        'The command took more than 60 seconds and was stopped.',
    'Esiste già un file {name}: dimmi se sovrascriverlo (overwrite) o aggiungere in fondo (append).':
        'A file {name} already exists: tell me whether to overwrite it (overwrite) or add to the end (append).',
    'Non trovo «{name}» {where}.':
        "I can't find «{name}» {where}.",
    "In {name} c'è già {name2}.":
        "There's already {name2} in {name}.",
    'Non trovo il file {name}.':
        "I can't find the file {name}.",
    'In {path}: ':
        'In {path}: ',
    'Non riesco a portare {app} in primo piano.':
        "I can't bring {app} to the front.",
    '{app} ha perso il focus mentre scrivevo: controlla il testo.':
        '{app} lost focus while I was typing: check the text.',
    'Non vedo «{wanted}» sullo schermo.':
        "I don't see «{wanted}» on the screen.",
    'Non trovo la città «{city}».':
        "I can't find the city «{city}».",
    'condizioni variabili':
        'variable conditions',
    'Il comando è fallito (codice {returncode}): {value}':
        'The command failed (code {returncode}): {value}',
    '\n[avvisi: {value}]':
        '\n[warnings: {value}]',
    'Windows non mi ha permesso di cestinare {kind} {name}.':
        "Windows didn't let me bin {kind} {name}.",
    'Esiste già qualcosa che si chiama {new_name} lì.':
        'Something called {new_name} already exists there.',
    '{app} non si è aperto entro {int} secondi.':
        "{app} didn't open within {int} seconds.",
    '{app} non si è aperto in tempo.':
        "{app} didn't open in time.",
    "Non vedo finestre di '{value}'.":
        "I don't see any windows of '{value}'.",
    '{capitalize}: {get}, min {round}° max {round2}°':
        '{capitalize}: {get}, low {round}° high {round2}°',
    "Non trovo l'app '{app}'.":
        "I can't find the app '{app}'.",
    'variabile':
        'variable',
    ', pioggia {rain}%':
        ', rain {rain}%',
    ' Forse: {names}?':
        ' Maybe: {names}?',
    ' Ho allegato uno screenshot di dove mi sono bloccata.':
        ' I attached a screenshot of where I got stuck.',
    'mancano gli argomenti: {join}':
        'missing arguments: {join}',
    'argomenti non validi':
        'invalid arguments',
    ' Ho salvato uno screenshot di dove mi sono bloccata in Immagini\\Ressy ({name}).':
        ' I saved a screenshot of where I got stuck in Pictures\\Ressy ({name}).',
    "argomento '{name}' non valido":
        "invalid argument '{name}'",
    "'{name}' deve essere uno tra: {join}":
        "'{name}' must be one of: {join}",
    "Lo strumento '{name}' non esiste o non è disponibile qui.":
        "The tool '{name}' doesn't exist or isn't available here.",
    "L'operazione ha impiegato troppo tempo ed è stata interrotta.":
        'The operation took too long and was stopped.',
    'Argomenti non validi: {exc}':
        'Invalid arguments: {exc}',
    'Errore imprevisto: {name}':
        'Unexpected error: {name}',
    'Azione non valida.':
        'Invalid action.',
    'Posso ricordare cose al massimo tra 30 giorni.':
        'I can remind you of things at most 30 days ahead.',
    'Non ci sono promemoria.':
        'There are no reminders.',
    'Promemoria:\n':
        'Reminders:\n',
    'il {due:%d/%m} alle {due:%H:%M}':
        'on {due:%b %d} at {due:%H:%M}',
    'Il promemoria deve essere nel futuro.':
        'The reminder must be in the future.',
    "Quando? Indica tra quanti minuti oppure l'orario (HH:MM).":
        'When? Say in how many minutes or the time (HH:MM).',
    'Cosa devo ricordarti?':
        'What should I remind you of?',
    'Promemoria impostato {when}: {text}.':
        'Reminder set {when}: {text}.',
    'Non ci sono promemoria da cancellare.':
        'There are no reminders to delete.',
    'Non trovo quel promemoria.':
        "I can't find that reminder.",
    'Ho cancellato il promemoria {when}: {text}.':
        'I deleted the reminder {when}: {text}.',
    'oggi alle {due:%H:%M}':
        'today at {due:%H:%M}',
    'domani alle {due:%H:%M}':
        'tomorrow at {due:%H:%M}',
    'Orario non valido: usa il formato HH:MM.':
        'Invalid time: use the HH:MM format.',
    'Orario non valido.':
        'Invalid time.',
    'Quale promemoria? ':
        'Which reminder? ',
    'Nessun promemoria con codice {wanted_id}.':
        'No reminder with code {wanted_id}.',
    'Testo copiato negli appunti.':
        'Text copied to the clipboard.',
    'Audio disattivato/riattivato.':
        'Sound muted/unmuted.',
    'Indica un livello (0-100) oppure change=up/down/mute.':
        'Give a level (0-100) or change=up/down/mute.',
    'PC bloccato.':
        'PC locked.',
    'Metto il PC in sospensione appena ho risposto.':
        "I'll put the PC to sleep as soon as I've answered.",
    'Spegnimento annullato.':
        'Shutdown cancelled.',
    'Ho aperto la cartella degli screenshot di Ressy.':
        "I opened Ressy's screenshots folder.",
    'Ho scritto il testo.':
        'I typed the text.',
    'Ho premuto play/pausa.':
        'I pressed play/pause.',
    'Traccia successiva.':
        'Next track.',
    'Traccia precedente.':
        'Previous track.',
    'Riproduzione fermata.':
        'Playback stopped.',
    'Screenshot salvato in Immagini\\Ressy ({name}).':
        'Screenshot saved in Pictures\\Ressy ({name}).',
    "Non c'era nessuno spegnimento programmato.":
        'There was no shutdown scheduled.',
    'batteria {percent:.0f}%, in carica':
        'battery {percent:.0f}%, charging',
    'batteria {percent:.0f}%, non in carica':
        'battery {percent:.0f}%, not charging',
    'Il PC è bloccato: non posso usare la tastiera finché non viene sbloccato.':
        "The PC is locked: I can't use the keyboard until it's unlocked.",
    'Testo troppo lungo (massimo 5000 caratteri).':
        'Text too long (5000 characters at most).',
    'Questa combinazione non si può inviare.':
        "This key combination can't be sent.",
    'Ho premuto {value}.':
        'I pressed {value}.',
    'Volume impostato al {level}%.':
        'Volume set to {level}%.',
    'Volume abbassato del {percent}%.':
        'Volume turned down by {percent}%.',
    'Screenshot fatto ({width}×{height}): lo allego alla risposta.':
        "Screenshot taken ({width}×{height}): I'm attaching it to the answer.",
    'Windows non ha bloccato il PC.':
        "Windows didn't lock the PC.",
    'Riavvio il PC tra {delay} secondi. Per annullare chiedimi di annullare il riavvio.':
        'Restarting the PC in {delay} seconds. To cancel, ask me to cancel the restart.',
    'RAM {percent:.0f}% ({used:.1f} di {total:.1f} GB)':
        'RAM {percent:.0f}% ({used:.1f} of {total:.1f} GB)',
    'Non trovo quella cartella.':
        "I can't find that folder.",
    'Ho aperto la cartella {raw_name}.':
        'I opened the folder {raw_name}.',
    'Ho aperto la cartella {value}.':
        'I opened the folder {value}.',
    'Ho aperto la cartella {basename} ({dirname}).':
        'I opened the folder {basename} ({dirname}).',
    ' Forse intendevi: {join}?':
        ' Did you mean: {join}?',
    "Non trovo una cartella '{raw_name}' nel Desktop, Documenti, Download o nella cartella utente.{hint}":
        "I can't find a folder '{raw_name}' on the Desktop, in Documents, in Downloads or in the user folder.{hint}",
    'Volume alzato del {percent}%.':
        'Volume turned up by {percent}%.',
    'Spengo il PC tra {delay} secondi. Per annullare chiedimi di annullare lo spegnimento.':
        'Shutting down the PC in {delay} seconds. To cancel, ask me to cancel the shutdown.',
    'disco {value:.0f} GB liberi su {value2:.0f}':
        'disk {value:.0f} GB free of {value2:.0f}',
    'acceso da {days}g {hours}h {value}m':
        'on for {days}d {hours}h {value}m',
    'acceso da {hours}h {value}m':
        'on for {hours}h {value}m',
    "{raw_name} è un programma, non una cartella: l'ho aperto.":
        '{raw_name} is a program, not a folder: I opened it.',
    'Apro solo indirizzi web (http/https).':
        'I only open web addresses (http/https).',
    'Non riesco ad aprire il browser predefinito.':
        "I can't open the default browser.",
    'Ho aperto {value} nel browser.':
        'I opened {value} in the browser.',
    'Cosa devo cercare?':
        'What should I search for?',
    'Ho cercato «{query}» su Google nel browser.':
        'I searched for «{query}» on Google in the browser.',
    'Cosa devo cercare su YouTube?':
        'What should I search for on YouTube?',
    'Qual è la domanda?':
        "What's the question?",
    'La ricerca non ha dato risultati utili.':
        'The search gave no useful results.',
    "'{raw}' non sembra un indirizzo web.":
        "'{raw}' doesn't look like a web address.",
    'Ho aperto i risultati di YouTube per «{query}»: scegli tu il video.':
        'I opened the YouTube results for «{query}»: pick the video yourself.',
    'Riproduco su YouTube: {title}.':
        'Playing on YouTube: {title}.',
    'Riproduco su YouTube il primo risultato per «{query}».':
        'Playing the first YouTube result for «{query}».',
    'Non riesco a spostare il mouse.':
        "I can't move the mouse.",
    'memoria insufficiente per gli appunti':
        'not enough memory for the clipboard',
    'impossibile preparare gli appunti':
        'cannot prepare the clipboard',
    'gli appunti sono occupati da un altro programma':
        'the clipboard is busy with another program',
    'Windows ha bloccato la tastiera simulata (finestra di un amministratore o PC bloccato?)':
        'Windows blocked the simulated keyboard (an administrator window, or the PC is locked?)',
    'SendInput non riuscito (errore {err})':
        'SendInput failed (error {err})',
    'tasto sconosciuto: {key}':
        'unknown key: {key}',
    'Nessuno':
        'None',
    'Ressy risponde solo alla tua voce, su questo PC.':
        'Ressy only answers your voice, on this PC.',
    'Il tuo bot, su questo PC':
        'Your bot, on this PC',
    'Crei un bot tuo su Telegram (o Discord) e Ressy lo fa girare qui. Niente da ospitare. Quando il PC è spento il bot tace; quando si riaccende ti scrive che è di nuovo online e non esegue i messaggi arrivati nel frattempo.':
        "You create your own bot on Telegram (or Discord) and Ressy runs it here. Nothing to host. When the PC is off the bot stays quiet; when it's back on, it tells you it's online again and doesn't run the messages that arrived in the meantime.",
    'Il tuo server (self-host)':
        'Your server (self-host)',
    'Il bot gira su una macchina tua sempre accesa (un altro PC, un Raspberry, un VPS) e ti avvisa subito quando questo PC va offline. Puoi installare il server con questo stesso installer.':
        'The bot runs on an always-on machine of yours (another PC, a Raspberry, a VPS) and tells you right away when this PC goes offline. You can install the server with this same installer.',
    'Telegram: scrivi {botfather} <code>/newbot</code>, scegli un nome e copia il token. Discord (facoltativo): {portal} → New Application → Bot → Reset Token. I token restano su questo PC, cifrati da Windows.':
        'Telegram: message {botfather} <code>/newbot</code>, pick a name and copy the token. Discord (optional): {portal} → New Application → Bot → Reset Token. The tokens stay on this PC, encrypted by Windows.',
    'Il token non deve contenere spazi.':
        'The token must not contain spaces.',
    "Scrivi l'indirizzo del tuo server, per esempio ws://192.168.1.10:8765/ws/agent.":
        'Write the address of your server, for example ws://192.168.1.10:8765/ws/agent.',
    "L'indirizzo del server inizia con ws:// (rete di casa) o wss:// (Internet, con HTTPS).":
        'The server address starts with ws:// (home network) or wss:// (Internet, with HTTPS).',
    '123456789:AA…':
        '123456789:AA…',
    'Token Telegram':
        'Telegram token',
    'Token Discord':
        'Discord token',
    'Il token Telegram ha la forma 123456789:AA… (lo trovi nel messaggio di BotFather).':
        "The Telegram token looks like 123456789:AA… (you'll find it in BotFather's message).",
    'Il token Discord è lungo e ha due punti: copialo da Bot → Reset Token.':
        'The Discord token is long and has two dots: copy it from Bot → Reset Token.',
    'Indirizzo del server':
        'Server address',
    'Incolla il token del tuo bot Telegram (o Discord).':
        'Paste the token of your Telegram (or Discord) bot.',
    'Il più rapido, sbaglia di più':
        'The fastest, makes more mistakes',
    'Buon equilibrio, consigliato':
        'Good balance, recommended',
    'Capisce meglio, più lento':
        'Understands better, slower',
    'Velocissimo, con piano gratuito.':
        'Very fast, with a free plan.',
    'Gratis':
        'Free',
    'gsk_…':
        'gsk_…',
    'Di Google, piano gratuito generoso.':
        'By Google, generous free plan.',
    'AIza…':
        'AIza…',
    'Tanti modelli gratis: ottima riserva.':
        'Lots of free models: a great backup.',
    'sk-or-v1-…':
        'sk-or-v1-…',
    'Il più capace. A consumo, a pagamento.':
        'The most capable. Pay as you go.',
    'Il più capace':
        'Most capable',
    'sk-ant-…':
        'sk-ant-…',
    'Gratis e offline, scaricata sul PC.':
        'Free and offline, downloaded to the PC.',
    'Senza chiave':
        'No key',
    'Nessuna':
        'None',
    'Solo le chiavi online':
        'Online keys only',
    'Meno di 500 MB: apre app, siti, musica, meteo':
        'Under 500 MB: opens apps, sites, music, weather',
    'Capisce meglio le richieste lunghe, 1-2 secondi':
        'Understands long requests better, 1-2 seconds',
    'Gratis e senza limiti. Funziona anche offline.':
        'Free and unlimited. Works offline too.',
    'Consigliato':
        'Recommended',
    'Whisper online, il più preciso. Usa la chiave Groq.':
        'Online Whisper, the most accurate. Uses the Groq key.',
    'Online, con la chiave Gemini.':
        'Online, with the Gemini key.',
    'Mostra':
        'Show',
    'Verifica':
        'Check',
    'Chiave API':
        'API key',
    'Puoi inserire <b>più chiavi</b>: scegli una scheda, incolla la chiave, poi torna su quella che vuoi usare. Se la prima arriva al limite, Ressy continua con le altre.':
        'You can enter <b>several keys</b>: pick a tab, paste the key, then go back to the one you want to use. If the first one reaches its limit, Ressy carries on with the others.',
    'Chiave valida.':
        'Valid key.',
    'Scarica':
        'Download',
    "Aspetta che finisca il download dell'AI sul PC.":
        'Wait for the AI download to the PC to finish.',
    "Scarico l'AI sul PC…":
        'Downloading the AI to the PC…',
    'La voce viene inviata a Groq (Whisper large v3) con la tua chiave Groq: è il più preciso, ma conta nei limiti del tuo piano gratuito.':
        "Your voice is sent to Groq (Whisper large v3) with your Groq key: it's the most accurate, but it counts towards your free plan's limits.",
    'La voce viene inviata a Gemini con la tua chiave Gemini.':
        'Your voice is sent to Gemini with your Gemini key.',
    'Scarico il modello…':
        'Downloading the model…',
    'GPT-OSS 120B (consigliato)':
        'GPT-OSS 120B (recommended)',
    'GPT-OSS 20B (più veloce)':
        'GPT-OSS 20B (faster)',
    'Qwen 3.8 27B':
        'Qwen 3.8 27B',
    "Gemini Flash, sempre l'ultimo (consigliato)":
        'Gemini Flash, always the latest (recommended)',
    'Gemini Flash-Lite (più veloce)':
        'Gemini Flash-Lite (faster)',
    'Gemini Pro (più capace, più lento)':
        'Gemini Pro (more capable, slower)',
    'Il miglior modello gratis del giorno (automatico)':
        'The best free model of the day (automatic)',
    'Modello':
        'Model',
    "Ressy pensa con un'AI scaricata su questo PC: gratis, senza chiave e anche senza internet. È meno brava dei servizi online, ma per aprire app, siti, musica e meteo basta.":
        "Ressy thinks with an AI downloaded to this PC: free, no key and even without internet. It's not as good as the online services, but it's enough to open apps, sites, music and weather.",
    'Incolla prima la chiave.':
        'Paste the key first.',
    "SCEGLI L'AI SUL PC":
        'CHOOSE THE AI ON THE PC',
    'RISERVA GRATUITA SUL PC (FACOLTATIVA)':
        'FREE BACKUP ON THE PC (OPTIONAL)',
    'Scegli quale AI scaricare sul PC.':
        'Choose which AI to download to the PC.',
    "Scarica l'AI sul PC (pulsante «Scarica»).":
        'Download the AI to the PC («Download» button).',
    "Scarica l'AI sul PC (pulsante «Scarica»), oppure scegli «Nessuna».":
        'Download the AI to the PC («Download» button), or choose «None».',
    'Annulla':
        'Cancel',
    'Download annullato.':
        'Download cancelled.',
    'Il modello si scarica una volta sola dentro la cartella di Ressy; poi la voce non esce dal PC.':
        "The model is downloaded only once, into Ressy's folder; after that your voice never leaves the PC.",
    'Aspetta che finisca il download del modello vocale.':
        'Wait for the speech model download to finish.',
    'Scarica il modello vocale (pulsante «Scarica»), oppure scegli di capire la voce online.':
        'Download the speech model («Download» button), or choose to understand speech online.',
    'Incolla la chiave API di {value} (è gratis crearla).':
        'Paste the {value} API key (creating one is free).',
    'Scaricata':
        'Downloaded',
    'Chiave inserita':
        'Key entered',
    'Chiave {name}':
        '{name} key',
    'Verifico la chiave con {value}…':
        'Checking the key with {value}…',
    'Download in corso…':
        'Downloading…',
    'Se tutte le chiavi sono al limite Ressy aspetta che si ricarichino.':
        'If all the keys are at their limit, Ressy waits for them to refill.',
    "Scarico l'AI sul PC… {value:.0f} di {value2:.0f} MB":
        'Downloading the AI to the PC… {value:.0f} of {value2:.0f} MB',
    "<span style='color:#FF8C73'>Download non riuscito</span>: controlla la connessione e riprova.":
        "<span style='color:#FF8C73'>Download failed</span>: check the connection and try again.",
    'Per capire la voce con {value} serve anche la sua chiave (pagina Intelligenza).':
        'To understand speech with {value} you also need its key (Brain page).',
    'Scarico il modello… {value:.0f} di {value2:.0f} MB':
        'Downloading the model… {value:.0f} of {value2:.0f} MB',
    'Ressy pensa con {name} usando la <b>tua</b> chiave: resta su questo PC, cifrata da Windows. ':
        'Ressy thinks with {name} using <b>your</b> key: it stays on this PC, encrypted by Windows. ',
    'Da scaricare':
        'To download',
    'Si scarica una volta: il modello Qwen 2.5 (Apache 2.0) e il motore llama.cpp ufficiale. Servono circa 2 GB di RAM libera quando è accesa.':
        "Downloaded once: the Qwen 2.5 model (Apache 2.0) and the official llama.cpp engine. It needs about 2 GB of free RAM while it's on.",
    '{label} · {mb} MB':
        '{label} · {mb} MB',
    'Scaricato':
        'Downloaded',
    "Si scaricherà durante l'installazione.":
        'It will be downloaded during the installation.',
    'Nascondi':
        'Hide',
    'Crea una chiave su {value}':
        'Create a key on {value}',
    '{name} ha rifiutato questa chiave: controlla di averla copiata tutta.':
        '{name} rejected this key: check that you copied all of it.',
    'Non riesco a raggiungere {name} ora: controlla la connessione e riprova.':
        "I can't reach {name} right now: check the connection and try again.",
    "<span style='color:{BACKLIGHT}'>Modello pronto</span> ({mb} MB).":
        "<span style='color:{BACKLIGHT}'>Model ready</span> ({mb} MB).",
    'Scarica ({mb} MB)':
        'Download ({mb} MB)',
    "<span style='color:{BACKLIGHT}'>AI sul PC pronta</span>: si accende solo quando serve e si spegne da sola dopo 10 minuti.":
        "<span style='color:{BACKLIGHT}'>AI on the PC ready</span>: it turns on only when needed and turns itself off after 10 minutes.",
    'Scarica ({size_text})':
        'Download ({size_text})',
    'Da scaricare: circa {mb} MB.':
        'To download: about {mb} MB.',
    'Metti Ressy a dormire':
        'Put Ressy to sleep',
    'Dorme':
        'Asleep',
    'Tu':
        'You',
    'Ascolta':
        'Listening',
    'Telegram/Discord: offline':
        'Telegram/Discord: offline',
    'Telegram/Discord: online, puoi comandare il PC dal telefono':
        'Telegram/Discord: online, you can control the PC from your phone',
    'Telegram/Discord: mi sto collegando al server…':
        'Telegram/Discord: connecting to the server…',
    'Comandi da Telegram/Discord disattivati':
        'Commands from Telegram/Discord turned off',
    'Telegram/Discord: il server ha rifiutato questo PC':
        'Telegram/Discord: the server refused this PC',
    'Telegram/Discord: aggiorna Ressy per collegarti':
        'Telegram/Discord: update Ressy to connect',
    'Telegram/Discord: Ressy è attiva su un altro PC con la stessa identità':
        'Telegram/Discord: Ressy is active on another PC with the same identity',
    'Telegram/Discord: il tuo bot non è partito, controlla il token':
        "Telegram/Discord: your bot didn't start, check the token",
    'Pausa':
        'Pause',
    'Bloc Scorr':
        'Scroll Lock',
    'Ins':
        'Ins',
    'Num *':
        'Num *',
    'Num +':
        'Num +',
    'Num -':
        'Num -',
    'Num ,':
        'Num ,',
    'Num /':
        'Num /',
    'Tasto {vk:#04x}':
        'Key {vk:#04x}',
    'Num {value}':
        'Num {value}',
    'Premi il nuovo tasto (Esc annulla)':
        'Press the new key (Esc cancels)',
    'Tasto per parlare: {name}. Premi per cambiarlo.':
        'Talk key: {name}. Press to change it.',
    'Codice di collegamento: {code}':
        'Link code: {code}',
    'Codice QR del link di Telegram':
        'QR code of the Telegram link',
    'Ressy · Collega Telegram o Discord':
        'Ressy · Link Telegram or Discord',
    'Collega il telefono':
        'Link your phone',
    'Dal bot di Telegram o Discord potrai dare comandi a questo PC, anche con un messaggio vocale. Il codice vale una volta sola.':
        "From your Telegram or Discord bot you'll be able to give commands to this PC, voice messages included. The code works only once.",
    'Chiedo un codice al bot…':
        'Asking the bot for a code…',
    'Copia il codice':
        'Copy the code',
    'Apri Telegram':
        'Open Telegram',
    'Copia il comando':
        'Copy the command',
    'Aggiungi il bot':
        'Add the bot',
    'Nuovo codice':
        'New code',
    'Chiudi':
        'Close',
    'Usa questo codice dal telefono:':
        'Use this code from your phone:',
    'Copiato':
        'Copied',
    'Il controllo da remoto non è configurato: in Impostazioni › Da remoto scegli il tuo bot e incolla il token.':
        "Remote control isn't set up: in Settings › Remote choose your bot and paste the token.",
    'Il server non ha bot attivi: chiedi a chi lo gestisce di configurarli.':
        'The server has no active bots: ask whoever runs it to set them up.',
    'Il codice è scaduto: chiedine uno nuovo.':
        'The code has expired: ask for a new one.',
    '!collega {code}':
        '!link {code}',
    'Collegato: {get} su {platform}. Ora puoi scrivere al bot.':
        'Linked: {get} on {platform}. You can now write to the bot.',
    'Scade tra {value}:{value2:02d}':
        'Expires in {value}:{value2:02d}',
    "Inquadra il QR con il telefono, oppure apri il link: il bot ti collega da solo.<br><span style='color:{LEGEND_DIM}'>{get}</span>":
        "Scan the QR code with your phone, or open the link: the bot links you by itself.<br><span style='color:{LEGEND_DIM}'>{get}</span>",
    'Ciao! Sono Ressy. Questa è la mia voce.':
        "Hi! I'm Ressy. This is my voice.",
    'Generale':
        'General',
    'Intelligenza':
        'Brain',
    'Voce':
        'Voice',
    'Tasto e ascolto':
        'Key and listening',
    'Da remoto':
        'Remote',
    'Ressy · Impostazioni':
        'Ressy · Settings',
    'Salva':
        'Save',
    'Come vuoi che Ressy ti chiami':
        'What should Ressy call you',
    'Il tuo nome':
        'Your name',
    'Lingua':
        'Language',
    'Automatica (posizione approssimativa del PC)':
        'Automatic (approximate location of the PC)',
    'Città per il meteo':
        'City for the weather',
    "Avvia Ressy all'accensione del PC":
        'Start Ressy when the PC turns on',
    'Se la chiave scelta è al limite, continua con le altre chiavi inserite':
        'If the chosen key is at its limit, carry on with the other keys entered',
    "Esegui i comandi semplici sul PC senza usare l'AI (apri app e siti, meteo, volume…)":
        'Run simple commands on the PC without using the AI (open apps and sites, weather, volume…)',
    "Avvisami quando c'è una nuova versione di Ressy e installala con un clic":
        "Tell me when there's a new version of Ressy and install it with one click",
    'Aggiorna':
        'Refresh',
    'Motore':
        'Engine',
    'Velocità':
        'Speed',
    "Suoni dell'interfaccia (tasto, risveglio, fine)":
        'Interface sounds (key, wake-up, end)',
    'Prova la voce':
        'Test the voice',
    'Tasto per parlare':
        'Talk key',
    'Tienilo premuto per':
        'Hold it for',
    'ressy sveglia, sveglia ressy':
        'ressy wake up, hey ressy',
    'Frasi di risveglio':
        'Wake phrases',
    'Quando è sveglia':
        'When awake',
    ' s di silenzio':
        ' s of silence',
    'Si addormenta dopo':
        'Falls asleep after',
    'Altoparlanti':
        'Speakers',
    'Nome di questo PC':
        'Name of this PC',
    'Collega Telegram o Discord…':
        'Link Telegram or Discord…',
    'Leggi ad alta voce sul PC le risposte ai comandi remoti':
        'Read aloud on the PC the answers to remote commands',
    'Mostra una notifica sul PC per ogni comando remoto':
        'Show a notification on the PC for each remote command',
    'Nuova identità per questo PC…':
        'New identity for this PC…',
    'Apri la cartella dei registri':
        'Open the logs folder',
    "Aggiorna l'elenco dei programmi":
        'Refresh the list of programs',
    'Predefinito di Windows':
        'Windows default',
    'Offline':
        'Offline',
    'Scollega account':
        'Unlink account',
    'Nuova identità':
        'New identity',
    'Creare una nuova identità per questo PC? Tutti gli account collegati verranno scollegati e dovrai ricollegarli con un nuovo codice.':
        "Create a new identity for this PC? All linked accounts will be unlinked and you'll have to link them again with a new code.",
    'Scrivi almeno una frase di risveglio, per esempio «ressy sveglia».':
        'Write at least one wake phrase, for example «ressy wake up».',
    'La lingua vale per le finestre, la voce, le risposte e le frasi di risveglio. Quando la cambi e salvi, Ressy si riavvia.':
        'The language applies to the windows, the voice, the answers and the wake phrases. When you change it and save, Ressy restarts.',
    "Ressy resta nell'area di notifica, accanto all'orologio. Se non parte con Windows, da Telegram e Discord risulterà offline finché non la apri.":
        "Ressy stays in the notification area, next to the clock. If it doesn't start with Windows, it will show as offline on Telegram and Discord until you open it.",
    'Scegli chi fa ragionare Ressy. Ognuno usa la <b>propria</b> chiave: niente piani condivisi, niente limiti di altri. Puoi cambiare quando vuoi.':
        "Choose who does Ressy's thinking. Everyone uses <b>their own</b> key: no shared plans, no one else's limits. You can change it whenever you want.",
    'Consumi delle chiavi':
        'Key usage',
    'Puoi anche chiederlo a voce o in chat: «quanto mi resta delle API?»':
        'You can also ask by voice or in chat: «how much API do I have left?»',
    'Capire la voce':
        'Understanding speech',
    'La voce di Ressy':
        "Ressy's voice",
    'La voce neurale richiede internet; la voce di Windows funziona anche offline. Se la prima non risponde, Ressy usa automaticamente la seconda.':
        "The neural voice needs internet; the Windows voice also works offline. If the first one doesn't respond, Ressy automatically uses the second.",
    'Un tocco veloce scrive la lettera come sempre; tenendo premuto parli con Ressy. Mentre Ressy dorme il microfono resta chiuso: si apre solo mentre tieni premuto il tasto.':
        'A quick tap types the letter as usual; holding it down lets you talk to Ressy. While Ressy sleeps the microphone stays closed: it opens only while you hold the key.',
    'Ressy non usa un bot condiviso: il bot è tuo, e gira su questo PC o su un tuo server.':
        "Ressy doesn't use a shared bot: the bot is yours, and it runs on this PC or on a server of yours.",
    'Account collegati':
        'Linked accounts',
    'Avanzate':
        'Advanced',
    'Solo gli account che colleghi con un codice possono comandare questo PC. Una nuova identità scollega tutti gli account.':
        'Only the accounts you link with a code can control this PC. A new identity unlinks all accounts.',
    "Le chiavi API e l'identità del PC sono cifrate con Windows (DPAPI) e valgono solo per il tuo utente su questo PC. I registri non contengono il testo dei messaggi.":
        "API keys and the PC identity are encrypted with Windows (DPAPI) and only work for your user on this PC. The logs don't contain the text of messages.",
    'Nessun account collegato.':
        'No linked accounts.',
    'Scollega':
        'Unlink',
    'Voce neurale Microsoft (online)':
        'Microsoft neural voice (online)',
    'Voce di Windows (offline)':
        'Windows voice (offline)',
    'Ascolta sempre: basta parlare':
        'Always listen: just talk',
    'Solo mentre tengo premuto il tasto':
        'Only while I hold the key',
    'Software libero con licenza MIT. ':
        'Free software under the MIT license. ',
    'chiave':
        'key',
    'Puoi comandare questo PC da Telegram e Discord.':
        'You can control this PC from Telegram and Discord.',
    'Mi sto collegando al bot.':
        'Connecting to the bot.',
    'Non riesco a raggiungere il server: riprovo da sola.':
        "I can't reach the server: I'll keep retrying by myself.",
    'I comandi da remoto sono disattivati, o manca il token del bot.':
        'Remote commands are turned off, or the bot token is missing.',
    'Il server ha rifiutato questo PC. Prova con una nuova identità.':
        'The server refused this PC. Try with a new identity.',
    'Questa versione di Ressy è troppo vecchia per il server: aggiornala.':
        'This version of Ressy is too old for the server: update it.',
    'Questa identità è in uso su un altro PC.':
        'This identity is in use on another PC.',
    'Scollegare {display} ({platform})? Non potrà più comandare questo PC finché non lo ricolleghi.':
        "Unlink {display} ({platform})? They won't be able to control this PC until you link them again.",
    "Non riesco a modificare l'avvio automatico di Windows.":
        "I can't change Windows' automatic startup.",
    'modello vocale':
        'speech model',
    'voce con':
        'speech with',
    '{current} (non collegato)':
        '{current} (not connected)',
    ' · dal {date}':
        ' · since {date}',
    '%d/%m/%Y':
        '%b %d, %Y',
    'Pensa':
        'Thinking',
    'Parla':
        'Speaking',
    'Online':
        'Online',
    'Mi collego…':
        'Connecting…',
    'Disattivato':
        'Off',
    'Rifiutato dal server':
        'Refused by the server',
    'Da aggiornare':
        'Needs an update',
    'Attiva su un altro PC':
        'Active on another PC',
    'Bot fermo':
        'Bot stopped',
    'Sveglia Ressy':
        'Wake Ressy up',
    'Interrompi la voce':
        'Stop talking',
    'Aggiorna Ressy…':
        'Update Ressy…',
    "Ressy · {label} · Telegram/Discord: {presence}\nTieni premuto {key} e di' «Ressy, sveglia!»":
        'Ressy · {label} · Telegram/Discord: {presence}\nHold {key} and say «Ressy, wake up!»',
    'Ressy · {label} · Telegram/Discord: {presence}':
        'Ressy · {label} · Telegram/Discord: {presence}',
    'Impostazioni…':
        'Settings…',
    'Esci da Ressy':
        'Quit Ressy',
    'Disinstalla Ressy':
        'Uninstall Ressy',
    'Vuoi disinstallare Ressy da questo PC?':
        'Do you want to uninstall Ressy from this PC?',
    "Tolgo l'app, i collegamenti, l'avvio con Windows e, se c'è, il server del tuo bot.":
        "I'll remove the app, the shortcuts, the start with Windows and, if there is one, your bot's server.",
    'Elimina anche impostazioni, chiavi e registri':
        'Also delete settings, keys and logs',
    'Disinstalla':
        'Uninstall',
    'Ressy è stata disinstallata. Grazie per averla provata!':
        'Ressy has been uninstalled. Thanks for trying it!',
    'Ressy · Aggiornamento':
        'Ressy · Update',
    'Più tardi':
        'Later',
    'Scarico…':
        'Downloading…',
    "Scarico l'aggiornamento…":
        'Downloading the update…',
    'Riprova':
        'Try again',
    'Installo: Ressy si chiude e riparte tra poco…':
        'Installing: Ressy closes and starts again shortly…',
    'È disponibile Ressy {version}':
        'Ressy {version} is available',
    "Hai la versione {version}. L'aggiornamento richiede un minuto: Ressy si chiude, si aggiorna e riparte da sola. Le tue impostazioni restano.":
        'You have version {version}. The update takes a minute: Ressy closes, updates and starts again by itself. Your settings stay.',
    'Aggiornamento non riuscito: {error}':
        'Update failed: {error}',
    "Scarico l'aggiornamento… {value:.0f} di {value2:.0f} MB":
        'Downloading the update… {value:.0f} of {value2:.0f} MB',
    "non riesco ad avviare l'installazione ({exc})":
        "I can't start the installation ({exc})",
    'Ressy, sveglia!':
        'Ressy, wake up!',
    'Così la svegli: tieni premuto K e dillo.':
        'This is how you wake her up: hold K and say it.',
    "Che meteo c'è?":
        "What's the weather like?",
    'Ressy capisce la domanda e legge il meteo.':
        'Ressy understands the question and reads the weather.',
    'Apri time.is sul browser':
        'Open time.is in the browser',
    'Ressy apre davvero il sito nel browser.':
        'Ressy really opens the site in the browser.',
    'il provider':
        'the provider',
    'Ci ho messo troppo: riprova.':
        'That took me too long: try again.',
    'Tieni premuto e parla':
        'Hold and speak',
    'Preparo il microfono e il modello…':
        'Preparing the microphone and the model…',
    'Cambio microfono…':
        'Switching microphone…',
    'Tieni premuto il pulsante (o la barra spaziatrice), parla, poi lascia.':
        'Hold the button (or the space bar), speak, then let go.',
    'Ci penso…':
        'Thinking…',
    'Qualcosa non è andato ({name}): riprova.':
        'Something went wrong ({name}): try again.',
    'Ti ascolto… lascia quando hai finito.':
        "I'm listening… let go when you're done.",
    'Tieni premuto mentre parli, poi lascia.':
        'Hold it while you speak, then let go.',
    'La chiave di {name} non è valida: torna indietro e controllala.':
        'The {name} key is not valid: go back and check it.',
    'Non riesco a raggiungere {name}: controlla la connessione.':
        "I can't reach {name}: check the connection.",
    'Il microfono predefinito di Windows non manda suono: uso «{name}». Puoi sceglierne un altro qui sopra.':
        "The Windows default microphone sends no sound: I'm using «{name}». You can choose another one above.",
    'Non ho sentito parole: avvicinati al microfono e riprova.':
        "I didn't hear any words: get closer to the microphone and try again.",
    'Ho sentito «{heard}». ':
        'I heard «{heard}». ',
    "Di' «<b>{say}</b>»":
        'Say «<b>{say}</b>»',
    "<span style='color:#FF8C73'>Non trovo un microfono</span> ({value}). Collegane uno e riapri l'installazione, oppure vai avanti e prova dopo.":
        "<span style='color:#FF8C73'>I can't find a microphone</span> ({value}). Plug one in and reopen the installer, or go ahead and try later.",
    "<span style='color:#FF8C73'>Non riesco a preparare la prova</span>: {error}":
        "<span style='color:#FF8C73'>I can't prepare the test</span>: {error}",
    'Non era la frase di risveglio: riprova.':
        "That wasn't the wake phrase: try again.",
    'Non ho capito cosa fare: riprova.':
        "I didn't understand what to do: try again.",
    "<span style='color:{BACKLIGHT}'>Tutto a posto</span>: Ressy ti sente e ti capisce.":
        "<span style='color:{BACKLIGHT}'>All good</span>: Ressy hears you and understands you.",
    'il file scaricato non corrisponde a quello pubblicato: riprova più tardi':
        "the downloaded file doesn't match the published one: try again later",
    'Installa':
        'Install',
    'Prova':
        'Test',
    'Telegram e Discord':
        'Telegram and Discord',
    'Installazione':
        'Installation',
    'Fatto':
        'Done',
    'Chiudo Ressy…':
        'Closing Ressy…',
    'Copio i file…':
        'Copying the files…',
    'Fatto: riavvio Ressy…':
        'Done: restarting Ressy…',
    'Aggiorno Ressy':
        'Updating Ressy',
    'Un momento…':
        'One moment…',
    'Chiudo Ressy, se è aperta…':
        "Closing Ressy, if it's open…",
    'Salvo le impostazioni…':
        'Saving the settings…',
    'Creo i collegamenti…':
        'Creating the shortcuts…',
    'Avvio con Windows…':
        'Start with Windows…',
    'Installa Ressy':
        'Install Ressy',
    'Indietro':
        'Back',
    'Avanti':
        'Next',
    "L'assistente vocale per Windows: tieni premuto K e di' «Ressy, sveglia!». Si installa solo per il tuo utente, senza permessi da amministratore.":
        'The voice assistant for Windows: hold K and say «Ressy, wake up!». It installs just for your user, with no administrator rights.',
    "Ressy, l'assistente vocale":
        'Ressy, the voice assistant',
    'Ressy Server (self-host), per un PC sempre acceso':
        'Ressy Server (self-host), for an always-on PC',
    'Fa girare il tuo bot Telegram/Discord giorno e notte per i tuoi PC e ti avvisa quando uno va offline. Non serve se vuoi che il bot giri dentro Ressy su questo PC.':
        'Runs your Telegram/Discord bot day and night for your PCs and tells you when one goes offline. Not needed if you want the bot to run inside Ressy on this PC.',
    'Sfoglia…':
        'Browse…',
    'Collegamento sul desktop':
        'Desktop shortcut',
    'Avvia Ressy con Windows':
        'Start Ressy with Windows',
    'Cartella di Ressy':
        "Ressy's folder",
    "L'intelligenza di Ressy":
        "Ressy's brain",
    'Chi capisce cosa chiedi e decide cosa fare sul PC. Ognuno usa la propria chiave API: crearla è gratis e richiede un minuto.':
        'It understands what you ask and decides what to do on the PC. Everyone uses their own API key: creating one is free and takes a minute.',
    'Come ti ascolta':
        'How it listens to you',
    'Per capire la tua voce Ressy può usare un piccolo modello sul PC, gratis e senza limiti, oppure un servizio online con la tua chiave.':
        'To understand your voice Ressy can use a small model on the PC, free and unlimited, or an online service with your key.',
    'Proviamo':
        "Let's try",
    'Tre prove vere con il tuo microfono, prima di finire: Ressy deve sentirti e capirti. Avanti si sblocca quando sono riuscite tutte e tre.':
        'Three real tests with your microphone before finishing: Ressy has to hear and understand you. Next unlocks when all three have worked.',
    'Nessun bot condiviso: ognuno usa il proprio, così nessuno si pesta i piedi. Puoi cambiare idea quando vuoi nelle impostazioni di Ressy.':
        "No shared bot: everyone uses their own, so nobody gets in anyone's way. You can change your mind anytime in Ressy's settings.",
    'Porta':
        'Port',
    'Ressy su questo PC si collegherà da sola a questo server.':
        'Ressy on this PC will connect to this server by itself.',
    'Installo…':
        'Installing…',
    'Ressy è installata':
        'Ressy is installed',
    'Avvia Ressy ora':
        'Start Ressy now',
    'Il pacchetto di installazione è danneggiato: scaricalo di nuovo.':
        'The installation package is damaged: download it again.',
    'Ressy.exe è ancora in uso: chiudi Ressy e riprova.':
        'Ressy.exe is still in use: close Ressy and try again.',
    'Il server del tuo bot':
        "Your bot's server",
    'Ferma il server del bot':
        'Stop the bot server',
    'Disinstalla Ressy.lnk':
        'Uninstall Ressy.lnk',
    'Software libero, licenza MIT.<br>Si installa solo per il tuo utente.':
        'Free software, MIT license.<br>Installs just for your user.',
    'Cosa installare':
        'What to install',
    'Dove':
        'Where',
    'Ressy Server':
        'Ressy Server',
    'Il bot del server: i tuoi PC si collegano a lui.':
        "The server's bot: your PCs connect to it.",
    'Fine':
        'Finish',
    'Incolla il token del bot per il server.':
        'Paste the bot token for the server.',
    'il modello sul PC':
        'the model on the PC',
    'Avvia Ressy Server ora':
        'Start Ressy Server now',
    'versione {version}':
        'version {version}',
    'Ressy Server.lnk':
        'Ressy Server.lnk',
    'Ferma Ressy Server.lnk':
        'Stop Ressy Server.lnk',
    'Scegli almeno una cosa da installare.':
        'Choose at least one thing to install.',
    'Scegli una cartella.':
        'Choose a folder.',
    'Ressy è in <b>{value}</b>. La trovi nel menu Start; si disinstalla da Impostazioni › App, come ogni altro programma.':
        "Ressy is in <b>{value}</b>. You'll find it in the Start menu; you can uninstall it from Settings › Apps, like any other program.",
    'Per comandarla dal telefono: icona di Ressy › «Collega Telegram o Discord…» e scrivi il codice al tuo bot.':
        "To control it from your phone: Ressy's icon › «Link Telegram or Discord…» and send the code to your bot.",
    'Aggiornamento non riuscito: {error}\nPuoi scaricare Ressy da ressy.top.':
        'Update failed: {error}\nYou can download Ressy from ressy.top.',
    'Scarico il modello vocale ({mb} MB)…':
        'Downloading the speech model ({mb} MB)…',
    'Installazione non riuscita: {error}':
        'Installation failed: {error}',
    "Ressy pensa con <b>{brain}</b> e ti ascolta con <b>{ear}</b>. Tieni premuto K e di' «Ressy, sveglia!».":
        'Ressy thinks with <b>{brain}</b> and listens to you with <b>{ear}</b>. Hold K and say «Ressy, wake up!».',
    '<code>ws://IP-di-questo-PC:{value}/ws/agent</code>':
        '<code>ws://IP-of-this-PC:{value}/ws/agent</code>',
    "Ressy Server parte con Windows. Sugli altri PC, in Ressy › Impostazioni › Da remoto, scegli «Il tuo server» e scrivi {where}. Se Windows chiede di consentire l'accesso alla rete, consenti le reti private.":
        'Ressy Server starts with Windows. On the other PCs, in Ressy › Settings › Remote, choose «Your server» and write {where}. If Windows asks to allow network access, allow private networks.',
    'Percorso non valido nel pacchetto: {name}':
        'Invalid path in the package: {name}',
    'Il modello vocale non si è scaricato ({exc}): Ressy te lo riproporrà nelle impostazioni.':
        "The speech model didn't download ({exc}): Ressy will offer it again in the settings.",
    'Scarico il modello vocale… {value:.0f} di {value2:.0f} MB':
        'Downloading the speech model… {value:.0f} of {value2:.0f} MB',
    ' Wi-Fi: {ssid}.':
        ' Wi-Fi: {ssid}.',
    ' per {to}':
        ' for {to}',
    '1 minuto':
        '1 minute',
    '1 ora':
        '1 hour',
    '1 secondo':
        '1 second',
    'Aggiorno le note…':
        'Updating notes…',
    'Azione del mouse non valida.':
        'Invalid mouse action.',
    'Azione di sistema non valida.':
        'Invalid system action.',
    'Azione finestra non valida.':
        'Invalid window action.',
    'Azione non valida per gli appunti.':
        'Invalid clipboard action.',
    'Azione non valida per le note.':
        'Invalid notes action.',
    'Azione programmata':
        'Scheduled action',
    'Azione programmata saltata (il PC era spento): {command}':
        'Scheduled action skipped (the PC was off): {command}',
    'Azione timer non valida.':
        'Invalid timer action.',
    'Cerco i file…':
        'Searching files…',
    'Connesso. IP locale: {ip}.{wifi}':
        'Connected. Local IP: {ip}.{wifi}',
    'Cosa devo cercare nei file?':
        'What should I search for in your files?',
    'Cosa devo segnare?':
        'What should I write down?',
    'Cronometro avviato.':
        'Stopwatch started.',
    'Cronometro fermato a {span}.':
        'Stopwatch stopped at {span}.',
    'Cronometro: {span}.':
        'Stopwatch: {span}.',
    'Discord':
        'Discord',
    'Ecco le note:\n':
        'Here are your notes:\n',
    'Eseguirò «{command}» tra {span}.':
        'I will run «{command}» in {span}.',
    "Esiste già l'archivio {name}.":
        'The archive {name} already exists.',
    'Gestisco gli appunti…':
        'Managing clipboard…',
    'Gestisco timer e cronometro…':
        'Managing timers and stopwatch…',
    'Gli appunti sono vuoti (o non contengono testo).':
        'The clipboard is empty (or has no text).',
    'Ho affiancato {label} a destra.':
        'I snapped {label} to the right.',
    'Ho affiancato {label} a sinistra.':
        'I snapped {label} to the left.',
    'Ho annullato il timer «{text}».':
        'I cancelled the timer «{text}».',
    'Ho aperto le impostazioni di Windows ({page}).':
        'I opened Windows settings ({page}).',
    'Ho aperto {kind} {name}.':
        'I opened {kind} {name}.',
    'Ho attivato la modalità chiara.':
        'I switched to light mode.',
    'Ho attivato la modalità scura.':
        'I switched to dark mode.',
    'Ho attivato o tolto lo schermo intero su {label}.':
        'I toggled fullscreen on {label}.',
    'Ho cancellato tutte le note.':
        'I cleared all notes.',
    'Ho cercato «{query}» su {site} nel browser.':
        'I searched for «{query}» on {site} in the browser.',
    'Ho cliccato alle coordinate {x}, {y}.':
        'I clicked at {x}, {y}.',
    'Ho compresso {name} in {archive}.':
        'I compressed {name} into {archive}.',
    'Ho estratto {name} {where}.':
        'I extracted {name} {where}.',
    'Ho fatto clic destro alle coordinate {x}, {y}.':
        'I right-clicked at {x}, {y}.',
    'Ho fatto doppio clic alle coordinate {x}, {y}.':
        'I double-clicked at {x}, {y}.',
    'Ho incollato dagli appunti.':
        'I pasted from the clipboard.',
    'Ho ingrandito {label}.':
        'I maximized {label}.',
    'Ho mostrato il desktop riducendo a icona le finestre.':
        'I showed the desktop by minimizing the windows.',
    'Ho preparato la bozza email{to}.':
        'I prepared the email draft{to}.',
    'Ho ridotto a icona {label}.':
        'I minimized {label}.',
    'Ho ripristinato {label}.':
        'I restored {label}.',
    'Ho scorso a destra.':
        'Scrolled right.',
    'Ho scorso a sinistra.':
        'Scrolled left.',
    'Ho scorso verso il basso.':
        'Scrolled down.',
    "Ho scorso verso l'alto.":
        'Scrolled up.',
    'Ho svuotato gli appunti.':
        'I cleared the clipboard.',
    'Ho svuotato il Cestino.':
        'I emptied the Recycle Bin.',
    'Ho svuotato la lista {category}.':
        'I cleared the {category} list.',
    'Ho tolto «{text}» dalle note.':
        'I removed «{text}» from your notes.',
    'Ho trovato e aperto {name} ({where}).':
        'I found and opened {name} ({where}).',
    'Ho trovato {count} risultato/i:\n':
        'Found {count} result(s):\n',
    'Il PC non sembra connesso a Internet o alla rete locale.':
        'The PC does not seem connected to the Internet or local network.',
    'Il PC è bloccato: non posso gestire le finestre finché non viene sbloccato.':
        'The PC is locked: I cannot manage windows until it is unlocked.',
    'Il PC è bloccato: non posso usare Discord finché non viene sbloccato.':
        'The PC is locked: I cannot use Discord until it is unlocked.',
    'Il cronometro non è avviato.':
        'The stopwatch is not running.',
    'Il riconoscimento del testo di Windows non è disponibile per leggere Discord.':
        'Windows text recognition is not available to read Discord.',
    'Indica la durata del timer (secondi o minuti).':
        'Tell me how long the timer should be (seconds or minutes).',
    'Indica la percentuale di luminosità (0-100).':
        'Specify the brightness percentage (0-100).',
    'Indica le coordinate (x, y) o usa click_text per cliccare una scritta.':
        'Provide (x, y) coordinates or use click_text to click on text.',
    'Indica le coordinate (x, y) per il clic destro.':
        'Provide (x, y) coordinates for the right click.',
    'Indica le coordinate (x, y) per il doppio clic.':
        'Provide (x, y) coordinates for the double click.',
    "L'archivio contiene percorsi non sicuri.":
        'The archive contains unsafe paths.',
    'La finestra di {name} è ridotta a icona.':
        'The {name} window is minimized.',
    'La pagina non contiene testo leggibile.':
        'The page has no readable text.',
    'Leggo Discord…':
        'Reading Discord…',
    'Leggo la pagina web…':
        'Reading the webpage…',
    'Luminosità abbassata al {level}%.':
        'Brightness lowered to {level}%.',
    'Luminosità alzata al {level}%.':
        'Brightness raised to {level}%.',
    'Luminosità impostata al {level}%.':
        'Brightness set to {level}%.',
    'Messaggi visibili in {target}:\n{text}':
        'Visible messages in {target}:\n{text}',
    'Muovo il mouse…':
        'Moving the mouse…',
    "Negli appunti c'è:\n{text}":
        'On the clipboard:\n{text}',
    'Nessun timer con codice {wanted_id}.':
        'No timer with code {wanted_id}.',
    "Non c'è nessuna finestra attiva.":
        'There is no active window.',
    'Non ci sono note in {category}.':
        'There are no notes in {category}.',
    'Non ci sono timer attivi da annullare.':
        'There are no active timers to cancel.',
    'Non ci sono timer attivi.':
        'There are no active timers.',
    'Non hai nessuna nota salvata.':
        'You have no saved notes.',
    'Non ho trovato nessun file o cartella per «{query}».':
        'I could not find any file or folder for «{query}».',
    'Non leggo i dischi.':
        'I cannot read the drives.',
    'Non posso aprire indirizzi locali o privati.':
        'I cannot open local or private addresses.',
    'Non posso calcolare la radice di un numero negativo.':
        'I cannot compute the square root of a negative number.',
    'Non riesco a leggere il testo nella finestra di Discord.':
        'I cannot read the text in the Discord window.',
    'Non riesco a portare {label} in primo piano.':
        'I cannot bring {label} to the front.',
    'Non riesco a trovare il sito {host}.':
        'I cannot find the site {host}.',
    'Non sono riuscita a leggere la pagina ({exc}).':
        'I could not read the page ({exc}).',
    'Non trovo quella nota.':
        'I cannot find that note.',
    'Non vedo messaggi leggibili nella chat di {target}.':
        'I do not see readable messages in {target}.',
    'Posso impostare timer al massimo per 30 giorni.':
        'I can set timers for at most 30 days.',
    'Preparo l’email…':
        'Preparing the email…',
    'Programmi che usano più RAM:\n':
        'Programs using the most RAM:\n',
    'Quale nota devo togliere?':
        'Which note should I remove?',
    'Quale testo devo copiare negli appunti?':
        'What text should I copy to the clipboard?',
    'Questo schermo non permette di regolare la luminosità da Windows.':
        'This display does not allow adjusting brightness from Windows.',
    'Regolo le impostazioni del PC…':
        'Adjusting PC settings…',
    'Segnato in {category}: {text}.':
        'Added to {category}: {text}.',
    'Segnato nelle note: {text}.':
        'Added to notes: {text}.',
    'Sistemo la finestra…':
        'Arranging the window…',
    'Sono passata alla finestra precedente.':
        'Switched to the previous window.',
    'Tengo sempre in primo piano {label}.':
        'Keeping {label} always on top.',
    'Timer':
        'Timer',
    'Timer attivi:\n':
        'Active timers:\n',
    'Timer impostato per {span}: {label}.':
        'Timer set for {span}: {label}.',
    'Timer scaduto: {text}.':
        'Timer finished: {text}.',
    'Windows non ha svuotato il Cestino.':
        'Windows did not empty the Recycle Bin.',
    '[{id}] {text} (tra {span})':
        '[{id}] {text} (in {span})',
    'la finestra':
        'the window',
    'la finestra attiva':
        'the active window',
    '{drive} {free:.0f} GB liberi su {total:.0f} GB':
        '{drive} {free:.0f} GB free of {total:.0f} GB',
    '{label} non è più fissata in primo piano.':
        '{label} is no longer pinned on top.',
    '{name} non è un archivio .zip.':
        '{name} is not a .zip archive.',
    '{n} minuti':
        '{n} minutes',
    '{n} ore':
        '{n} hours',
    '{n} secondi':
        '{n} seconds',
    "Ressy, l'assistente vocale AI per desktop.":
        'Ressy, the AI voice assistant for desktop.',
    "llama-server non trovato nell'archivio":
        'llama-server was not found in the archive',
    'Edito il video…':
        'Editing the video…',
    'Il riconoscimento del testo sullo schermo non è disponibile per leggere Discord.':
        'Screen text recognition is not available to read Discord.',
    'Il riconoscimento del testo sullo schermo non è disponibile.':
        'Screen text recognition is not available.',
    'Nessun gestore appunti trovato (xclip, xsel o wl-copy).':
        'No clipboard helper found (xclip, xsel or wl-copy).',
    'Impossibile aprire: xdg-open non è installato.':
        'Cannot open: xdg-open is not installed.',
    'Specifica i tasti da premere.':
        'Specify the keys to press.',
    "Tasto sconosciuto: '{token}'.":
        "Unknown key: '{token}'.",
    'Spengo il PC tra {delay} secondi.':
        'Shutting down the PC in {delay} seconds.',
    'Riavvio il PC tra {delay} secondi.':
        'Restarting the PC in {delay} seconds.',
    'Ho aperto le impostazioni di sistema ({page}).':
        'Opened system settings ({page}).',
    "Carica almeno un file video per iniziare l'editing.":
        'Upload at least one video file to start editing.',
    'DaVinci Resolve non sembra installato su questo PC, ma ho preparato tutto il pacchetto timeline (.fcpxml, sfondo, frasi PNG ed .srt) in {folder}.{preview}':
        'DaVinci Resolve does not appear installed on this PC, but I prepared the full timeline bundle (.fcpxml, background, PNG phrases and .srt) in {folder}.{preview}',
    'CapCut su Linux non ha un client desktop nativo: scegli DaVinci Resolve oppure attiva render_preview.':
        'CapCut does not have a native Linux desktop client: pick DaVinci Resolve or enable render_preview.',
    'Progetto CapCut «{project}» creato con successo ({clips} clip, sfondo, {phrases} frasi ad impatto, effetti) in {path}.{preview}':
        'CapCut project "{project}" created ({clips} clips, background, {phrases} impact phrases, effects) at {path}.{preview}',
    ' Anteprima MP4 esportata: {path}.':
        ' Preview MP4 exported: {path}.',
    'Editing completato su DaVinci Resolve! Progetto «{project}» aperto nella pagina Edit con {clips} clip, sfondo, {phrases} frasi ad impatto e sottotitoli ({ratio}).{preview}':
        'DaVinci Resolve editing complete! Project "{project}" opened on the Edit page with {clips} clips, background, {phrases} impact phrases and captions ({ratio}).{preview}',
    'Ho preparato il progetto DaVinci Resolve «{project}» ({clips} clip, sfondo, {phrases} frasi ad impatto ed effetti) e ho aperto DaVinci Resolve: importa {xml} da File > Import > Timeline per caricare la timeline completa.{preview}':
        'Prepared DaVinci Resolve project "{project}" ({clips} clips, background, {phrases} impact phrases and effects) and opened DaVinci Resolve: import {xml} via File > Import > Timeline to load the full timeline.{preview}',
    'Ho aperto {editor} ed è tutto pronto! Carica o dimmi i video da editare (percorso o nome file in Download/Video): poi aggiungerò sfondo, effetti e frasi ad impatto.':
        'Opened {editor} and everything is ready! Upload or tell me which videos to edit (file path or name in Downloads/Videos), then I will add background, effects and impact phrases.',
    'Non trovo questi file video: {files}. Controlla il nome o il percorso.':
        'Cannot find these video files: {files}. Check the file name or path.',
    ' Anteprima esportata: {path}.':
        ' Preview exported: {path}.',
    'Editing completato su CapCut! Ho creato il progetto «{project}» con {clips} clip, sfondo personalizzato, {phrases} frasi ad impatto, effetti e ritmo ({ratio}).{preview} CapCut è aperto con il progetto pronto.':
        'CapCut editing complete! Created project "{project}" with {clips} clips, custom background, {phrases} impact phrases, effects and pacing ({ratio}).{preview} CapCut is open with your project ready.',
    'Ressy · Carica i video da editare':
        'Ressy · Upload videos to edit',
    'Carica i video da editare':
        'Upload videos to edit',
    'Trascina i video qui sotto oppure scegli i file. Ressy aggiungerà sfondo, effetti e frasi ad impatto su CapCut o DaVinci Resolve.':
        'Drop your videos below or choose files. Ressy will add background, effects and impact phrases in CapCut or DaVinci Resolve.',
    'Scegli video…':
        'Choose videos…',
    'Rimuovi selezionato':
        'Remove selected',
    'Automatico (usa quello installato)':
        'Automatic (use installed editor)',
    'Viral / TikTok / Reels (dinamico + testi grandi)':
        'Viral / TikTok / Reels (dynamic + bold text)',
    'Cinematic (transizioni morbide + titoli eleganti)':
        'Cinematic (smooth transitions + sleek titles)',
    'Gaming / Highlight (zoom veloci + neon)':
        'Gaming / Highlight (punchy zoom + neon)',
    'Vlog (pulito + sottotitoli)':
        'Vlog (clean + captions)',
    'Verticale 9:16 (TikTok / Reels / Shorts)':
        'Vertical 9:16 (TikTok / Reels / Shorts)',
    'Orizzontale 16:9 (YouTube)':
        'Landscape 16:9 (YouTube)',
    'Quadrato 1:1':
        'Square 1:1',
    'Es. NON CI CREDERAI MAI (opzionale)':
        'E.g. YOU WON’T BELIEVE THIS (optional)',
    'Frasi ad impatto separate da virgola (opzionale)':
        'Impact phrases separated by commas (optional)',
    'Esporta anche un MP4 finito pronto subito (oltre al progetto)':
        'Also export a finished MP4 preview right away (in addition to the project)',
    'Editor video':
        'Video editor',
    'Stile montaggio':
        'Edit style',
    'Formato':
        'Aspect ratio',
    'Titolo iniziale':
        'Opening hook title',
    'Frasi ad impatto':
        'Impact phrases',
    'Inizia editing':
        'Start editing',
    "Seleziona i video o l'audio":
        'Select videos or audio',
    'Video e audio (*.mp4 *.mov *.mkv *.webm *.avi *.m4v *.mp3 *.wav);;Tutti i file (*)':
        'Video and audio (*.mp4 *.mov *.mkv *.webm *.avi *.m4v *.mp3 *.wav);;All files (*)',
    'Carica almeno un video prima di iniziare.':
        'Upload at least one video before starting.',
    '(eseguito senza output)':
        '(ran with no output)',
    'Codice Python troppo lungo.':
        'Python code is too long.',
    'Download non riuscito: {err}':
        'Download failed: {err}',
    'Equilibrio ideale su PC, capisce più comandi':
        'Balanced for a PC, understands more commands',
    'Eseguo uno script Python…':
        'Running a Python script…',
    'File troppo grande (massimo 500 MB).':
        'File is too large (500 MB max).',
    'Fino a 2 GB: massima intelligenza offline per fare tutto':
        'Up to 2 GB: maximum offline intelligence to handle everything',
    'Ho scaricato {name} ({size:.1f} MB) in {folder}.':
        'Downloaded {name} ({size:.1f} MB) to {folder}.',
    'Il comando ha impiegato più di 120 secondi ed è stato interrotto.':
        'The command took more than 120 seconds and was stopped.',
    'Lo script Python ha superato il limite di tempo ({s}s).':
        'The Python script exceeded the time limit ({s}s).',
    'Lo script Python è fallito (codice {returncode}): {value}':
        'The Python script failed (exit code {returncode}): {value}',
    'Manca il codice Python da eseguire.':
        'Missing Python code to run.',
    'Massima':
        'Maximum',
    'Non modifico le cartelle di sistema del sistema operativo.':
        'I do not modify operating system folders.',
    'Questo script può danneggiare il sistema: non lo eseguo.':
        'This script could harm the system: I will not run it.',
    'Scarico il file…':
        'Downloading file…',
    'Audio':
        'Audio',
    'Sfondo dinamico':
        'Dynamic backdrop',
    'Non trovo questi file video: {files}. Controlla il nome o il percorso.{hint}':
        'Cannot find these video files: {files}. Check the file name or path.{hint}',
    'Studio avviato · analisi di {n} clip ({dur:.1f}s)…':
        'Studio started · analyzing {n} clips ({dur:.1f}s)…',
    'Analisi clip video…':
        'Analyzing video clips…',
    'Sorgente ({w}×{h})':
        'Source ({w}×{h})',
    'Creazione sfondo dinamico & preparazione color grading ({grade})…':
        'Building dynamic backdrop & preparing color grading ({grade})…',
    'Creo sfondo & look…':
        'Creating backdrop & look…',
    'Sfondo & color grading ({grade})':
        'Backdrop & color grading ({grade})',
    'Trascrizione audio & generazione titoli / sottotitoli sincronizzati…':
        'Transcribing audio & generating synced titles / captions…',
    'Genero sottotitoli…':
        'Generating captions…',
    'Compositing titoli ({n} card)':
        'Compositing titles ({n} cards)',
    'Applico keyframe zoom, transizioni ({tr}) e auto-ducking audio…':
        'Applying zoom keyframes, transitions ({tr}) and audio ducking…',
    'Applico transizioni & FX…':
        'Applying transitions & FX…',
    'Costruisco la timeline completa su {editor}…':
        'Building the full timeline in {editor}…',
    'Esporto timeline {editor}…':
        'Exporting {editor} timeline…',
    'CapCut non supportato su Linux.':
        'CapCut is not supported on Linux.',
    'Apertura progetto in CapCut…':
        'Opening project in CapCut…',
    'Esportazione MP4 finale & apertura automatica di CapCut…':
        'Exporting final MP4 & auto-opening CapCut…',
    'Apro CapCut…':
        'Opening CapCut…',
    'Render video finale…':
        'Rendering final video…',
    'Render finale MP4':
        'Final MP4 render',
    'Editing completato su CapCut!':
        'CapCut editing complete!',
    'Video pronto!':
        'Video ready!',
    'Invio timeline a DaVinci Resolve & render anteprima…':
        'Sending timeline to DaVinci Resolve & rendering preview…',
    'Apro DaVinci Resolve…':
        'Opening DaVinci Resolve…',
    'Editing completato!':
        'Editing complete!',
    'Video disponibili trovati: {names}.':
        'Available videos found: {names}.',
    'Smooth Fade / Dissolve':
        'Smooth Fade / Dissolve',
    'Zoom Whip dinamico':
        'Dynamic Zoom Whip',
    'Flash cinematografico':
        'Cinematic Flash',
    'Nessuna transizione (cut netti)':
        'No transition (hard cuts)',
    'Vivido / Social Pop':
        'Vivid / Social Pop',
    'Teal & Orange Cinematic':
        'Teal & Orange Cinematic',
    'Pellicola contrastata':
        'High-contrast Film',
    'Naturale (nessuna alterazione)':
        'Natural (no grading)',
    "Sottotitoli automatici sincronizzati dall'audio":
        'Auto captions synced from audio',
    'Barra di avanzamento moderna nella parte bassa':
        'Modern bottom progress bar',
    'Transizioni':
        'Transitions',
    'Color grading':
        'Color grading',
    'Ressy Studio · Live Editing':
        'Ressy Studio · Live Editing',
    'Nuovo progetto video':
        'New video project',
    'In preparazione':
        'Preparing',
    'ANTEPRIMA COMPOSITO LIVE':
        'LIVE COMPOSITE PREVIEW',
    'In attesa dei fotogrammi…':
        'Waiting for frames…',
    "L'anteprima visiva comparirà qui durante il montaggio…":
        'The visual preview will appear here while editing…',
    'Preparazione pipeline di montaggio…':
        'Preparing editing pipeline…',
    'OPERAZIONI DI EDITING':
        'EDITING PIPELINE',
    'Analisi clip & audio':
        'Clip & audio analysis',
    'Sfondo studio & grafiche':
        'Studio backdrop & graphics',
    'Trascrizione & sottotitoli':
        'Transcription & captions',
    'REGISTRO STUDIO':
        'STUDIO LOG',
    'Color grading, FX & transizioni':
        'Color grading, FX & transitions',
    'Timeline, keyframe & progetto':
        'Timeline, keyframes & project',
    'Apri video finale':
        'Open final video',
    'Render MP4 & apertura editor':
        'MP4 render & open editor',
    'Apri cartella progetto':
        'Open project folder',
    'Editing live':
        'Editing live',
    'Caricamento fotogrammi in corso…':
        'Loading frames…',
    'Analisi':
        'Analysis',
    'Avvio studio di montaggio…':
        'Starting editing studio…',
    'Completato':
        'Completed',
    'Errore':
        'Error',
    "Manca l'URL del tuo server AI: inseriscilo nelle impostazioni di Ressy.":
        'Your AI server URL is missing: enter it in Ressy settings.',
    "Inserisci l'URL del tuo server AI (Impostazioni › Intelligenza) o avviane uno sul PC.":
        'Enter your AI server URL (Settings › Brain) or start one on this PC.',
    'Il tuo server AI':
        'Your AI server',
    'Voce + Audio':
        'Voice + Audio',
    'Impostazione inquadratura & preparazione color grading ({grade})…':
        'Setting framing & preparing color grading ({grade})…',
    'Creo inquadratura & look…':
        'Creating framing & look…',
    'Look & Color grading ({grade})':
        'Look & Color grading ({grade})',
    'Trascrizione audio & sincronizzazione sottotitoli parola per parola…':
        'Transcribing audio & syncing word-by-word captions…',
    'Sincronizzo parole…':
        'Syncing words…',
    'Sottotitoli dinamici ({n} card)':
        'Dynamic captions ({n} cards)',
    'Creazione slide 3D Grid B-Roll, badge animati, punch zoom & SFX ({tr})…':
        'Creating 3D Grid B-Roll slides, animated badges, zoom punches & SFX ({tr})…',
    'Creo B-Roll 3D & SFX…':
        'Creating 3D B-Roll & SFX…',
    'B-Roll 3D & grafiche':
        '3D B-Roll & graphics',
    'Timeline FX':
        'FX Timeline',
    'Questo PC (8088)':
        'This PC (8088)',
    'Opzionale (lascia vuoto se non serve)':
        'Optional (leave blank if not required)',
    'Connetti':
        'Connect',
    'Automatico dal server (o scrivi il nome esatto)':
        'Auto from server (or type exact model name)',
    'URL server AI':
        'AI server URL',
    'Token (opzionale)':
        'Token (optional)',
    'CREA IL TUO SERVER PER IL MODELLO (HOST SU QUESTO PC)':
        'CREATE YOUR OWN MODEL SERVER (HOST ON THIS PC)',
    'Scegli .gguf…':
        'Choose .gguf…',
    'Accessibile anche in rete / altri PC (0.0.0.0)':
        'Accessible on network / other PCs (0.0.0.0)',
    'Genera token':
        'Generate token',
    'Crea e avvia server AI':
        'Create & start AI server',
    'Puoi servire un modello Qwen già scaricato o un qualsiasi file .gguf, poi collegarci Ressy o un altro PC.':
        'You can serve a downloaded Qwen model or any .gguf file, then connect Ressy or another PC.',
    "Inserisci l'URL del tuo server AI o avvia un server su questo PC.":
        'Enter your AI server URL or start a server on this PC.',
    'Configurato':
        'Configured',
    'Collega Ressy a un <b>tuo</b> server AI OpenAI-compatibile (Ollama, LM Studio, llama.cpp o VPS), oppure creane e avviamone uno direttamente da qui sotto.':
        'Connect Ressy to <b>your own</b> OpenAI-compatible AI server (Ollama, LM Studio, llama.cpp or VPS), or create and launch one right below.',
    'Nessun file .gguf trovato (scegli o scarica sotto)':
        'No .gguf file found (choose or download below)',
    'Scegli modello GGUF':
        'Choose GGUF model',
    'Ferma server AI':
        'Stop AI server',
    "<span style='color:{BACKLIGHT}'>Server attivo</span> · Connettiti a: <b>{urls}</b>":
        "<span style='color:{BACKLIGHT}'>Server running</span> · Connect at: <b>{urls}</b>",
    'Server AI fermato.':
        'AI server stopped.',
    'Scegli prima un file .gguf (oppure scarica un modello locale qui sotto).':
        'Choose a .gguf file first (or download a local model below).',
    'Avvio il server del modello AI…':
        'Starting the AI model server…',
    'Avvio non riuscito: {err}':
        'Startup failed: {err}',
    'Server AI creato e connesso!':
        'AI server created and connected!',
    'Usa il tuo server (Ollama, llama.cpp, VPS…).':
        'Use your own server (Ollama, llama.cpp, VPS…).',
    'Self-host':
        'Self-host',
    'Inserisci prima un URL valido (es. http://127.0.0.1:8088/v1).':
        'Enter a valid URL first (e.g. http://127.0.0.1:8088/v1).',
    'Connessione a {url}…':
        'Connecting to {url}…',
    'Server connesso! Trovati {n} modelli.':
        'Server connected! Found {n} models.',
    'Server connesso!':
        'Server connected!',
    "Sottotitoli automatici sincronizzati dall'audio (parola per parola)":
        'Auto captions synced from audio (word by word)',
    'Dinamici parola per parola (stile TikTok / Reels)':
        'Dynamic word by word (TikTok / Reels style)',
    'Card ad impatto classiche':
        'Classic impact cards',
    'Slide 3D / Grafiche B-Roll ed effetti sonori (whoosh, pop)':
        '3D Slides / B-Roll graphics & sound effects (whoosh, pop)',
    'Sottotitoli':
        'Captions',
    'Hai già provato esattamente questa chiamata ed è fallita: cambia argomenti/strumento o chiedi all\'utente.':
        'You already tried this exact call and it failed: change the arguments/tool or ask the user.',
    'A chi devo scrivere su Discord?':
        'Who should I write to on Discord?',
    'Avvio la chiamata…':
        'Starting the call…',
    'Le chiamate tramite Telegram Desktop sono supportate su Windows.':
        'Calls via Telegram Desktop are supported on Windows.',
    'Telegram Desktop non sembra installato o aperto su questo PC.':
        'Telegram Desktop does not appear to be installed or open on this PC.',
    'Ho aperto la chat Discord con {target}, ma non trovo il pulsante «Avvia chiamata vocale». Verifica che sia una chat privata (DM).':
        'I opened the Discord chat with {target}, but I cannot find the «Start Voice Call» button. Make sure it is a direct message (DM).',
    'corrente':
        'current',
    'Sto chiamando {target} su Discord!':
        'Calling {target} on Discord!',
    'Ho aperto la chat Telegram con {target}, ma non trovo il pulsante «Chiama» nella barra in alto.':
        'I opened the Telegram chat with {target}, but I cannot find the «Call» button in the top bar.',
    'Sto chiamando {target} su Telegram!':
        'Calling {target} on Telegram!',
    'Dimmi il contatto o @username Telegram da chiamare (puoi anche salvarlo in Impostazioni › Da remoto).':
        'Tell me the Telegram contact or @username to call (you can also save it in Settings › Remote).',
    'Dimmi il nome Discord da chiamare (puoi anche salvarlo in Impostazioni › Da remoto).':
        'Tell me the Discord name to call (you can also save it in Settings › Remote).',
    'Chiamata da Ressy sul tuo PC!':
        'Call from Ressy on your PC!',
    'Ti ho inviato anche un avviso vocale sul telefono.':
        'I also sent a voice alert to your phone.',
    'Non sono riuscita a far partire la chiamata desktop ({err}), ma ti ho inviato subito un avviso vocale su {plat}.':
        'I could not start the desktop call ({err}), but I sent a voice alert right away on {plat}.',
    'Non sono riuscita ad avviare la chiamata.':
        'I could not start the call.',
    'Promemoria con chiamata su {plat} impostato {when}: {text}.':
        'Reminder with a call on {plat} set {when}: {text}.',
    'es. nomeutente (opzionale, per chiamate)':
        'e.g. username (optional, for calls)',
    'Contatto Discord per chiamate':
        'Discord contact for calls',
    'es. @nomeutente (opzionale, per chiamate)':
        'e.g. @username (optional, for calls)',
    'Contatto Telegram per chiamate':
        'Telegram contact for calls',
    'Non vedo altri dispositivi attivi sulla rete Wi-Fi al momento. Dimmi l\'IP o il nome del dispositivo da chiamare.':
        'I do not see other active devices on the Wi-Fi network right now. Tell me the IP or name of the device to call.',
    'Quale dispositivo devo scegliere della tua rete?\n{devices}':
        'Which device on your network should I choose?\n{devices}',
    'Non trovo «{target}» sulla rete. Quale dispositivo devo scegliere della tua rete?\n{devices}':
        'I cannot find «{target}» on the network. Which device on your network should I choose?\n{devices}',
    'Non trovo il dispositivo «{target}» sulla rete Wi-Fi.':
        'I cannot find the device «{target}» on the Wi-Fi network.',
    'Chiamata Wi-Fi avviata verso {device}! Apri sul dispositivo: {url}':
        'Wi-Fi call started to {device}! Open on the device: {url}',
    'Non sono riuscita a completare la risposta, riprova.':
        'I could not finish the answer, please try again.',
    'Chiamata Wi-Fi da Ressy sul tuo PC!':
        'Wi-Fi call from Ressy on your PC!',
    'Ti ho inviato anche la notifica con il link sul telefono.':
        'I also sent the notification with the link to your phone.',
    'Ti ho inviato una chiamata vocale/notifica urgente su {plat}!':
        'I sent an urgent voice call/notification on {plat}!',
}
