(() => {
  "use strict";
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
  const now = () => performance.now();
  const pick = (list) => list[Math.floor(Math.random() * list.length)];
  const HOLD_MS = 350;
  const MIN_TALK_MS = 350;
  const AUTO_SLEEP_MS = 9e4;
  const ECHO_MS = 250;
  const STATE_LABELS = { asleep: "Dorme", listening: "Ascolta", hearing: "Ascolta", thinking: "Pensa", speaking: "Parla" };
  const TOOL_STATUS = {
    open_app: "Apro il programma…",
    close_app: "Chiudo il programma…",
    send_discord_message: "Scrivo su Discord…",
    play_youtube: "Cerco su YouTube…",
    web_answer: "Cerco sul web…",
    media_control: "Controllo la musica…",
    set_volume: "Regolo il volume…",
    take_screenshot: "Faccio uno screenshot…",
    pc_power: "Gestisco l’alimentazione…",
    type_text: "Scrivo…",
    reminder: "Gestisco i promemoria…"
  };
  const COLORS = { legend: "#E9E6DF", accent: "#9D6BFF", rest: "#3A3D46" };
  function dayPart(date = new Date()) {
    const h = date.getHours();
    if (h >= 5 && h < 13) return "Buongiorno";
    if (h >= 13 && h < 18) return "Buon pomeriggio";
    if (h >= 18) return "Buonasera";
    return "Ciao";
  }
  function greeting() {
    const part = dayPart();
    const options = [`${part}! Cosa posso fare per te?`, `${part}. Eccomi, dimmi pure.`, `${part}! Sono qui, ti ascolto.`];
    if ((new Date()).getHours() < 5) options.push("Ciao, si è fatto tardi! Dimmi pure.");
    return pick(options);
  }
  const farewell = () => pick(["A dopo!", "Va bene, a dopo.", "Ci sono se ti serve."]);
  function clipText(text, limit) {
    const t = String(text).split(/\s+/).filter(Boolean).join(" ");
    if (t.length <= limit) return t;
    let cut = t.slice(0, limit);
    const space = cut.lastIndexOf(" ");
    if (space >= 0) cut = cut.slice(0, space);
    return cut.replace(/[,.;:]+$/, "") + "…";
  }
  function mulberry32(seed) {
    let a = seed >>> 0;
    return () => {
      a = a + 1831565813 >>> 0;
      let t = a;
      t = Math.imul(t ^ t >>> 15, t | 1);
      t ^= t + Math.imul(t ^ t >>> 7, t | 61);
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }
  function gaussian(rng) {
    const u = 1 - rng();
    const v = rng();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  }
  const prefs = { sound: true };
  const Loop = {
    tickers: [],
    raf: 0,
    last: 0,
    add(fn) {
      this.tickers.push(fn);
    },
    wake() {
      if (this.raf) return;
      this.last = now();
      this.raf = requestAnimationFrame((t) => this.frame(t));
    },
    frame(t) {
      const dt = clamp(t - this.last, 1, 64);
      this.last = t;
      let more = false;
      for (const fn of this.tickers) if (fn(t, dt)) more = true;
      this.raf = more ? requestAnimationFrame((u) => this.frame(u)) : 0;
    }
  };
  const BANDS = 24;
  const LOW_HZ = 90;
  const HIGH_HZ = 7e3;
  function makeFFT(n) {
    const levels = Math.round(Math.log2(n));
    if (1 << levels !== n) throw new Error("FFT size must be a power of two");
    const cos = new Float64Array(n / 2);
    const sin = new Float64Array(n / 2);
    for (let i = 0; i < n / 2; i++) {
      cos[i] = Math.cos(2 * Math.PI * i / n);
      sin[i] = Math.sin(2 * Math.PI * i / n);
    }
    const rev = new Uint32Array(n);
    for (let i = 0; i < n; i++) {
      let r = 0;
      for (let b = 0, x = i; b < levels; b++, x >>= 1) r = r << 1 | x & 1;
      rev[i] = r;
    }
    return (re, im) => {
      for (let i = 0; i < n; i++) {
        const j = rev[i];
        if (j > i) {
          let t = re[i];
          re[i] = re[j];
          re[j] = t;
          t = im[i];
          im[i] = im[j];
          im[j] = t;
        }
      }
      for (let size = 2; size <= n; size <<= 1) {
        const half = size >> 1;
        const step = n / size;
        for (let i = 0; i < n; i += size) {
          for (let j = i, k = 0; j < i + half; j++, k += step) {
            const l = j + half;
            const tre = re[l] * cos[k] + im[l] * sin[k];
            const tim = im[l] * cos[k] - re[l] * sin[k];
            re[l] = re[j] - tre;
            im[l] = im[j] - tim;
            re[j] += tre;
            im[j] += tim;
          }
        }
      }
    };
  }
  function createMeter(n, rate) {
    const half = n >> 1;
    const val = 1 / (n * (1 / rate));
    const freq = (k) => k * val;
    const topHz = Math.min(HIGH_HZ, rate * 0.45);
    let top = 0;
    while (top <= half && freq(top) < topHz) top++;
    const logLo = Math.log10(LOW_HZ);
    const step = (Math.log10(topHz) - logLo) / BANDS;
    const starts = new Int32Array(BANDS);
    for (let i = 0; i < BANDS; i++) {
      const edge = i === 0 ? LOW_HZ : Math.pow(10, i * step + logLo);
      let s = 0;
      while (s < top && freq(s) < edge) s++;
      starts[i] = clamp(s, 0, top - 1);
    }
    const out = new Float32Array(BANDS);
    function bandsOf(spec2) {
      out.fill(0);
      if (top < 2) return out;
      for (let i = 0; i < BANDS; i++) {
        const s = starts[i];
        const e = i < BANDS - 1 ? starts[i + 1] : top;
        let peak = spec2[s];
        if (e > s) {
          for (let k = s + 1; k < e; k++) if (spec2[k] > peak) peak = spec2[k];
        }
        const db = 20 * Math.log10(peak + 1e-9);
        out[i] = clamp((db + 66) / 52, 0, 1);
      }
      return out;
    }
    let fft = null;
    let win = null;
    let re = null;
    let im = null;
    let spec = null;
    function analyse(x) {
      if (!fft) {
        fft = makeFFT(n);
        win = new Float64Array(n);
        for (let i = 0; i < n; i++) win[i] = 0.5 - 0.5 * Math.cos(2 * Math.PI * i / (n - 1));
        re = new Float64Array(n);
        im = new Float64Array(n);
        spec = new Float64Array(Math.max(top, 1));
      }
      for (let i = 0; i < n; i++) {
        re[i] = x[i] * win[i];
        im[i] = 0;
      }
      fft(re, im);
      for (let k = 0; k < top; k++) spec[k] = Math.hypot(re[k], im[k]) / (n / 4);
      return bandsOf(spec);
    }
    return { n, rate, top, starts, freq, bandsOf, analyse };
  }
  const AudioOut = {
    ctx: null,
    ensure() {
      if (!this.ctx) {
        const Ctx = window.AudioContext || window.webkitAudioContext;
        if (!Ctx) return null;
        try {
          this.ctx = new Ctx();
        } catch (err) {
          return null;
        }
      }
      if (this.ctx.state === "suspended") this.ctx.resume().catch(() => {
      });
      return this.ctx;
    }
  };
  const Cues = {
    buffers: new Map(),
    build(name, rate) {
      const env = (t, attack, decay) => clamp(t / Math.max(attack, 1e-4), 0, 1) * Math.exp(-t / Math.max(decay, 1e-4));
      const note2 = (f, dur, vol = 0.18, decay = 0.09) => {
        const n = Math.floor(rate * dur);
        const x2 = new Float32Array(n);
        for (let i = 0; i < n; i++) {
          const t = i / rate;
          x2[i] = vol * (Math.sin(2 * Math.PI * f * t) + 0.22 * Math.sin(2 * Math.PI * 2 * f * t)) * env(t, 4e-3, decay);
        }
        return x2;
      };
      const silence = (dur) => new Float32Array(Math.floor(rate * dur));
      const concat = (...parts) => {
        const out = new Float32Array(parts.reduce((a, p) => a + p.length, 0));
        let o = 0;
        for (const p of parts) {
          out.set(p, o);
          o += p.length;
        }
        return out;
      };
      let x;
      if (name === "thock") {
        const n = Math.floor(rate * 0.07);
        const rng = mulberry32(7);
        const noise = new Float64Array(n);
        for (let i = 0; i < n; i++) noise[i] = gaussian(rng);
        const taps = Math.max(1, Math.round(6 * rate / 24e3));
        const lead = Math.floor((taps - 1) / 2);
        const gain = Math.sqrt(taps / 6);
        x = new Float32Array(n);
        for (let i = 0; i < n; i++) {
          let acc = 0;
          for (let j = i + lead - taps + 1; j <= i + lead; j++) if (j >= 0 && j < n) acc += noise[j];
          const t = i / rate;
          const body = 0.22 * Math.sin(2 * Math.PI * 165 * t) * env(t, 1e-3, 0.018);
          const click = 0.1 * gain * (acc / taps) * env(t, 5e-4, 4e-3);
          x[i] = body + click;
        }
      } else if (name === "wake") {
        x = concat(note2(659.25, 0.09, 0.18, 0.05), note2(987.77, 0.22, 0.18, 0.1));
      } else if (name === "sleep") {
        x = concat(note2(987.77, 0.09, 0.18, 0.05), note2(659.25, 0.24, 0.18, 0.11));
      } else if (name === "error") {
        x = concat(note2(392, 0.11, 0.16, 0.06), silence(0.02), note2(311.13, 0.2, 0.16));
      } else {
        return null;
      }
      const fade = Math.min(Math.round(rate * 0.01), x.length);
      for (let j = 0; j < fade; j++) x[x.length - fade + j] *= fade > 1 ? 1 - j / (fade - 1) : 0;
      for (let i = 0; i < x.length; i++) x[i] = clamp(x[i], -1, 1);
      return x;
    },
    play(name) {
      if (!prefs.sound) return;
      const ctx = AudioOut.ensure();
      if (!ctx) return;
      let buffer = this.buffers.get(name);
      if (!buffer) {
        const data = this.build(name, ctx.sampleRate);
        if (!data) return;
        buffer = ctx.createBuffer(1, data.length, ctx.sampleRate);
        buffer.getChannelData(0).set(data);
        this.buffers.set(name, buffer);
      }
      const src = ctx.createBufferSource();
      src.buffer = buffer;
      src.connect(ctx.destination);
      src.start();
    }
  };
  const Mic = {
    on: false,
    stream: null,
    source: null,
    analyser: null,
    sink: null,
    buf: null,
    meter: null,
    onEnded: null,
    async start() {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        const err = new Error("unsupported");
        err.name = "Unsupported";
        throw err;
      }
      const ctx = AudioOut.ensure();
      if (!ctx) {
        const err = new Error("no audio");
        err.name = "Unsupported";
        throw err;
      }
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false }
      });
      this.stream = stream;
      this.source = ctx.createMediaStreamSource(stream);
      this.analyser = ctx.createAnalyser();
      this.analyser.fftSize = 2048;
      this.analyser.smoothingTimeConstant = 0;
      this.sink = ctx.createGain();
      this.sink.gain.value = 0;
      this.source.connect(this.analyser);
      this.analyser.connect(this.sink);
      this.sink.connect(ctx.destination);
      this.buf = new Float32Array(this.analyser.fftSize);
      this.meter = createMeter(1024, ctx.sampleRate);
      for (const track of stream.getAudioTracks()) {
        track.addEventListener("ended", () => {
          if (this.stream === stream) {
            this.stop();
            if (this.onEnded) this.onEnded();
          }
        });
      }
      this.on = true;
      Loop.wake();
    },
    stop() {
      this.on = false;
      if (this.stream) for (const track of this.stream.getTracks()) track.stop();
      for (const node of [this.source, this.analyser, this.sink]) {
        if (node) try {
          node.disconnect();
        } catch (err) {
        }
      }
      this.stream = this.source = this.analyser = this.sink = null;
    },
    bands() {
      if (!this.on || !this.analyser) return null;
      this.analyser.getFloatTimeDomainData(this.buf);
      return this.meter.analyse(this.buf.subarray(this.buf.length - 1024));
    }
  };
  const VOWEL_CHARS = "aeiouyàèéìíòóùú";
  const STRONG_CHARS = "aeoàèéìíòóùú";
  const ACCENTED = "àèéìíòóùú";
  const PLAIN = { à: "a", è: "e", é: "e", ì: "i", í: "i", ò: "o", ó: "o", ù: "u", ú: "u", y: "i" };
  const isVowel = (c) => VOWEL_CHARS.includes(c);
  const isStrong = (c) => STRONG_CHARS.includes(c);
  const plain = (c) => PLAIN[c] || c;
  function mainVowel(group) {
    for (const c of group) if (ACCENTED.includes(c)) return plain(c);
    for (const c of group) if ("aeo".includes(c)) return c;
    return plain(group[group.length - 1]);
  }
  function onsetKind(o, group) {
    if (!o) return "none";
    if (o[0] === "h") return onsetKind(o.slice(1), group);
    const soft = /^[eièéì]/.test(group);
    if (/sc$/.test(o) && soft) return "sh";
    if (o.length >= 2 && o[0] === "s") return "ptkc".includes(o[1]) ? "sstop" : "fric";
    const last = o[o.length - 1];
    if ((last === "c" || last === "g") && soft) return last === "c" ? "affr" : "vaffr";
    const c = o[0];
    if (c === "z") return "affr";
    if (c === "s" || c === "x") return "fric";
    if (c === "f") return "ffric";
    if (c === "v") return "vfric";
    if ("ptckq".includes(c)) return "stop";
    if (c === "g" && (o[1] === "n" || o[1] === "l")) return "son";
    if ("bdg".includes(c)) return "vstop";
    return "son";
  }
  function codaKind(c) {
    if (!c) return "none";
    if ("lmnr".includes(c[0])) return "son";
    if ("sfz".includes(c[0])) return "fric";
    return "stop";
  }
  function syllabify(raw) {
    const w = raw.toLowerCase().replace(/[’']/g, "");
    const made = (count, vowels, onset) => Array.from({ length: count }, (_, i) => ({
      onset,
      vowel: vowels[i % vowels.length],
      coda: "none",
      stress: i === count - 1,
      dur: i === count - 1 ? 190 : 140
    }));
    if (/^\d+$/.test(w)) return made(clamp(w.length + 1, 2, 6), ["i", "o", "a", "e"], "stop");
    if (raw.length > 1 && raw.length <= 4 && raw === raw.toUpperCase() && /[A-Z]/.test(raw)) {
      return made(raw.length, ["i"], "stop");
    }
    const nuclei = [];
    for (let i = 0; i < w.length; ) {
      if (!isVowel(w[i])) {
        i++;
        continue;
      }
      let j = i + 1;
      while (j < w.length && isVowel(w[j])) j++;
      let s = i;
      for (let k = i + 1; k < j; k++) {
        if (isStrong(w[k - 1]) && isStrong(w[k])) {
          nuclei.push([s, k]);
          s = k;
        }
      }
      nuclei.push([s, j]);
      i = j;
    }
    if (!nuclei.length) return made(1, ["e"], "fric");
    const out = nuclei.map(([s, e], n) => {
      const prevEnd = n === 0 ? 0 : nuclei[n - 1][1];
      return { cluster: w.slice(prevEnd, s), group: w.slice(s, e), codaLetters: "" };
    });
    out.forEach((syl, n) => {
      let onset = syl.cluster;
      if (n > 0 && onset.length >= 2) {
        const [a, b] = onset;
        if (a === b || "lmnr".includes(a) && b !== "h") {
          out[n - 1].codaLetters = a;
          onset = onset.slice(1);
        }
      }
      syl.onsetLetters = onset;
    });
    out[out.length - 1].codaLetters += w.slice(nuclei[nuclei.length - 1][1]);
    const accented = out.findIndex((s) => [...s.group].some((c) => ACCENTED.includes(c)));
    const stressAt = accented >= 0 ? accented : Math.max(0, out.length - 2);
    const mono = out.length === 1;
    return out.map((s, i) => {
      const stress = mono ? w.length >= 3 || accented >= 0 : i === stressAt;
      const coda = codaKind(s.codaLetters);
      const extra = Math.max(0, s.onsetLetters.length - 1) * 22 + (coda === "none" ? 0 : 45);
      return {
        onset: onsetKind(s.onsetLetters, s.group),
        vowel: mainVowel(s.group),
        coda,
        stress,
        dur: (stress ? 195 : i === out.length - 1 ? 150 : 135) + extra
      };
    });
  }
  function parseSpeech(text) {
    const words = [];
    const re = /[\p{L}\p{N}’']+/gu;
    let m;
    while (m = re.exec(text)) words.push({ start: m.index, end: m.index + m[0].length, text: m[0] });
    const syls = [];
    const first = [];
    let prev = "e";
    words.forEach((word, wi) => {
      const next = wi + 1 < words.length ? words[wi + 1].start : text.length;
      const between = text.slice(word.end, next);
      let pause = wi + 1 < words.length ? 35 : 0;
      if (/[,—–]/.test(between)) pause = 220;
      if (/[:;]/.test(between)) pause = 260;
      if (/[.!?…]/.test(between)) pause = 380;
      first.push(syls.length);
      const parts = syllabify(word.text);
      parts.forEach((s, si) => {
        s.prev = prev;
        prev = s.vowel;
        s.last = si === parts.length - 1;
        s.gap = s.last ? pause : 0;
        syls.push(s);
      });
    });
    const question = /\?\s*$/.test(text);
    syls.forEach((s, i) => {
      s.pos = syls.length > 1 ? i / (syls.length - 1) : 0;
      s.f0 = 228 - 34 * s.pos + (s.stress ? 14 : 0) + (question && i >= syls.length - 2 ? 45 : 0);
    });
    const duration = syls.reduce((a, s) => a + s.dur + s.gap, 0);
    return {
      words,
      syls,
      first,
      duration,
      wordAt(charIndex) {
        for (let i = 0; i < words.length; i++) if (charIndex < words[i].end) return i;
        return -1;
      },
      locate(w, t) {
        let i = first[w];
        if (i === void 0) return null;
        for (; i < syls.length; i++) {
          const s = syls[i];
          if (t < s.dur) return { s, u: t / s.dur };
          t -= s.dur;
          if (t < s.gap) return null;
          t -= s.gap;
        }
        return null;
      }
    };
  }
  const VoiceModel = (() => {
    const meter = createMeter(480, 24e3);
    const top = meter.top;
    const bin = meter.freq(1);
    const spec = new Float64Array(top);
    const binHz = Array.from({ length: top }, (_, k) => meter.freq(k));
    const VOWEL_F = { a: [850, 1400, 2800], e: [520, 2e3, 2800], i: [330, 2400, 3e3], o: [560, 1e3, 2700], u: [370, 900, 2600] };
    const NASAL_F = [280, 1250, 2700];
    const NOISE = { s: [5600, 0.45, -33], sh: [3300, 0.55, -35], f: [4500, 1.4, -50], burst: [2600, 1.3, -38] };
    const ONSET = { none: 0, son: 0.2, stop: 0.28, vstop: 0.26, fric: 0.34, ffric: 0.3, vfric: 0.3, sh: 0.34, affr: 0.34, vaffr: 0.3, sstop: 0.42 };
    const CODA = { none: 0, son: 0.2, stop: 0.22, fric: 0.25 };
    const SILENT = -Infinity;
    const lerpF = (a, b, p) => a.map((v, i) => v + (b[i] - v) * clamp(p, 0, 1));
    function hann(d) {
      d = Math.abs(d);
      if (d < 1e-6) return 1;
      if (Math.abs(d - 1) < 1e-6) return 0.5;
      const x = Math.PI * d;
      return Math.abs(Math.sin(x) / x / (1 - d * d));
    }
    function envelopeDb(f, F) {
      let db = f <= 300 ? 0 : -10 * Math.log2(f / 300);
      const peaks = [14, 12, 8];
      const widths = [0.22, 0.16, 0.13];
      for (let k = 0; k < 3; k++) {
        const d = Math.log2(f / F[k]) / widths[k];
        db += peaks[k] * Math.exp(-0.5 * d * d);
      }
      return db;
    }
    function segment(s, u) {
      const on = ONSET[s.onset] || 0;
      const cd = CODA[s.coda] || 0;
      const F = VOWEL_F[s.vowel] || VOWEL_F.e;
      if (u < on) {
        const p2 = u / on;
        switch (s.onset) {
          case "son":
            return { v: -7, F: lerpF(NASAL_F, F, p2 * 0.5) };
          case "stop":
            return p2 < 0.75 ? { v: SILENT } : { v: SILENT, noise: "burst" };
          case "vstop":
            return p2 < 0.75 ? { v: -24, F: NASAL_F } : { v: -10, F, noise: "burst", nd: -6 };
          case "fric":
            return { v: SILENT, noise: "s" };
          case "ffric":
            return { v: SILENT, noise: "f" };
          case "vfric":
            return { v: -14, F: NASAL_F, noise: "f", nd: -4 };
          case "sh":
            return { v: SILENT, noise: "sh" };
          case "affr":
            return p2 < 0.35 ? { v: SILENT } : { v: SILENT, noise: "sh" };
          case "vaffr":
            return p2 < 0.35 ? { v: -24, F: NASAL_F } : { v: -14, F, noise: "sh", nd: -6 };
          case "sstop":
            return p2 < 0.55 ? { v: SILENT, noise: "s" } : p2 < 0.85 ? { v: SILENT } : { v: SILENT, noise: "burst" };
          default:
            break;
        }
      }
      if (cd && u >= 1 - cd) {
        if (s.coda === "son") return { v: -6, F: NASAL_F };
        if (s.coda === "fric") return { v: SILENT, noise: "s", nd: -3 };
        return { v: SILENT };
      }
      const p = (u - on) / Math.max(1e-4, 1 - on - cd);
      const attack = p < 0.15 ? -9 * (1 - p / 0.15) : 0;
      const release = p > 0.75 ? (s.last && s.gap > 100 ? -18 : -6) * ((p - 0.75) / 0.25) : 0;
      const Fx = p < 0.3 ? lerpF(VOWEL_F[s.prev] || F, F, 0.5 + p / 0.6) : F;
      return { v: (s.stress ? 0 : -3) + attack + release, F: Fx };
    }
    function bands(s, u, t, rng) {
      spec.fill(0);
      const seg = segment(s, u);
      const gain = -15 - 4 * s.pos + (rng() - 0.5) * 2;
      if (seg.v > -60) {
        const f0 = s.f0 * (1 + 0.012 * Math.sin(2 * Math.PI * 5.5 * (t / 1e3)) + (rng() - 0.5) * 0.01);
        for (let h = 1; ; h++) {
          const f = h * f0;
          if (f > 7400) break;
          const a = Math.pow(10, (gain + seg.v + envelopeDb(f, seg.F)) / 20);
          const c = f / bin;
          const k0 = Math.max(0, Math.ceil(c - 6));
          const k1 = Math.min(top - 1, Math.floor(c + 6));
          for (let k = k0; k <= k1; k++) {
            const m = a * hann(k - c);
            if (m > spec[k]) spec[k] = m;
          }
        }
      }
      if (seg.noise) {
        const [center, width, level] = NOISE[seg.noise];
        const base = level + (seg.nd || 0) - 4 * s.pos;
        for (let k = 1; k < top; k++) {
          const d = Math.log2(binHz[k] / center) / width;
          const m = Math.pow(10, (base - 4.34 * d * d) / 20) * (Math.sqrt(-2 * Math.log(1 - rng())) / 1.2533);
          if (m > spec[k]) spec[k] = m;
        }
      }
      return meter.bandsOf(spec);
    }
    return { bands };
  })();
  const Voice = {
    synth: "speechSynthesis" in window ? window.speechSynthesis : null,
    voice: null,
    job: null,
    lastCancel: -1e9,
    unlocked: false,
    init() {
      if (!this.synth) return;
      const pickVoice = () => {
        const voices = this.synth.getVoices() || [];
        const it = voices.filter((v) => /^it([-_]|$)/i.test(v.lang || ""));
        const score = (v) => {
          const n = v.name || "";
          if (/isabella/i.test(n)) return 5;
          if (/elsa/i.test(n)) return 4;
          if (/natural|online/i.test(n)) return 3;
          if (/google/i.test(n)) return 2;
          return 1;
        };
        it.sort((a, b) => score(b) - score(a));
        this.voice = it[0] || null;
      };
      pickVoice();
      if (typeof this.synth.addEventListener === "function") this.synth.addEventListener("voiceschanged", pickVoice);
      else this.synth.onvoiceschanged = pickVoice;
      this.pickVoice = pickVoice;
    },
    get available() {
      if (this.synth && !this.voice && this.pickVoice) this.pickVoice();
      return Boolean(this.synth && this.voice);
    },
    unlock() {
      if (this.unlocked || !this.synth) return;
      this.unlocked = true;
      try {
        const u = new SpeechSynthesisUtterance(" ");
        u.volume = 0;
        this.synth.speak(u);
      } catch (err) {
      }
    },
    speaking(owner) {
      const job = this.job;
      return Boolean(job && !job.done && (!owner || job.owner === owner));
    },
    speak(text, owner) {
      this.cancel();
      const plan = parseSpeech(text);
      return new Promise((resolve) => {
        const job = { owner, plan, resolve, started: false, done: false, silent: false, word: 0, at: 0, rng: mulberry32(Math.random() * 2 ** 32 >>> 0) };
        this.job = job;
        const readingTime = clamp(text.length * 55, 1400, 6e3);
        const goSilent = () => {
          job.silent = true;
          job.timer = setTimeout(() => this.finish(job, true), readingTime);
        };
        if (!prefs.sound || !this.available) {
          goSilent();
          return;
        }
        const u = new SpeechSynthesisUtterance(text);
        u.voice = this.voice;
        u.lang = this.voice.lang;
        u.rate = 1;
        u.pitch = 1;
        u.volume = 1;
        u.onstart = () => {
          if (this.job !== job || job.started) return;
          job.started = true;
          job.word = 0;
          job.at = now();
          Loop.wake();
        };
        u.onboundary = (e) => {
          if (this.job !== job || e.name && e.name !== "word") return;
          const w = plan.wordAt(e.charIndex);
          if (w < 0) return;
          job.started = true;
          job.word = w;
          job.at = now();
          Loop.wake();
        };
        u.onend = () => this.finish(job, true);
        u.onerror = (e) => {
          if (this.job !== job || job.done) return;
          if (!job.started && e.error !== "interrupted" && e.error !== "canceled") {
            clearTimeout(job.safety);
            goSilent();
            return;
          }
          this.finish(job, false);
        };
        job.utterance = u;
        const delay = Math.max(0, this.lastCancel + 100 - now());
        job.timer = setTimeout(() => {
          if (this.job !== job) return;
          if (this.synth.paused) this.synth.resume();
          this.synth.speak(u);
          job.safety = setTimeout(() => {
            if (this.job === job && !job.done) {
              this.synth.cancel();
              this.finish(job, true);
            }
          }, plan.duration * 1.8 + 3e3);
        }, delay);
      });
    },
    cancel(owner) {
      const job = this.job;
      if (!job || owner && job.owner !== owner) return;
      if (!job.silent && this.synth) {
        this.synth.cancel();
        this.lastCancel = now();
      }
      this.finish(job, false);
    },
    finish(job, completed) {
      if (job.done) return;
      job.done = true;
      clearTimeout(job.timer);
      clearTimeout(job.safety);
      if (this.job === job) this.job = null;
      job.resolve(completed);
    },
    bandsFor(owner, t) {
      const job = this.job;
      if (!job || job.done || job.silent || !job.started || job.owner !== owner) return null;
      const at = job.plan.locate(job.word, Math.max(0, t - job.at));
      if (!at) return ZERO;
      return VoiceModel.bands(at.s, at.u, t, job.rng);
    }
  };
  const ZERO = new Float32Array(BANDS);
  class Lines {
    constructor(canvas, color) {
      this.canvas = canvas;
      this.ctx = canvas.getContext("2d");
      this.color = color;
      this.values = new Float32Array(24);
      this.target = new Float32Array(24);
      this.w = 0;
      this.h = 0;
      this.dpr = 1;
      if ("ResizeObserver" in window) new ResizeObserver(() => this.resize()).observe(canvas);
      else window.addEventListener("resize", () => this.resize());
      this.resize();
    }
    resize() {
      const r = this.canvas.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 3);
      const w = Math.round(r.width * dpr);
      const h = Math.round(r.height * dpr);
      if (w !== this.canvas.width || h !== this.canvas.height) {
        this.canvas.width = w;
        this.canvas.height = h;
      }
      this.w = r.width;
      this.h = r.height;
      this.dpr = dpr;
      this.draw();
    }
    feed(bands, dt) {
      const k = dt / 16;
      const attack = 1 - Math.pow(1 - 0.55, k);
      const release = 1 - Math.pow(1 - 0.16, k);
      for (let i = 0; i < 12; i++) {
        const g = Math.pow(Math.max(bands[2 * i], bands[2 * i + 1]), 0.85);
        this.target[11 - i] = g;
        this.target[12 + i] = g;
      }
      let moved = false;
      let rest = true;
      for (let i = 0; i < 24; i++) {
        const v = this.values[i];
        const t = this.target[i];
        let nv = v + (t - v) * (t > v ? attack : release);
        if (nv < 4e-3) nv = 0;
        if (Math.abs(nv - v) > 2e-3) moved = true;
        if (nv > 0) rest = false;
        this.values[i] = nv;
      }
      if (moved || rest && this.drawnActive) this.draw();
      return moved || !rest;
    }
    reset() {
      this.values.fill(0);
      this.draw();
    }
    draw() {
      const { ctx, w, h, dpr } = this;
      if (!ctx || w <= 0 || h <= 0) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      const n = 24;
      const total = n * 5 + (n - 1) * 4;
      const scale = Math.min(1, w / total);
      const bar = 5 * scale;
      const gap = 4 * scale;
      const r = bar / 2;
      const mid = h / 2;
      const span = h - bar;
      let x = 0;
      let active = false;
      for (let i = 0; i < n; i++) {
        const v = this.values[i];
        const bh = bar + v * span;
        const y = mid - bh / 2;
        ctx.fillStyle = v > 0.02 ? this.color : COLORS.rest;
        ctx.beginPath();
        ctx.arc(x + r, y + r, r, Math.PI, 0);
        ctx.arc(x + r, y + bh - r, r, 0, Math.PI);
        ctx.closePath();
        ctx.fill();
        if (v > 0) active = true;
        x += bar + gap;
      }
      this.drawnActive = active;
    }
  }
  class HudView {
    constructor(root, owner) {
      this.root = root;
      this.owner = owner;
      this.legend = $('[data-role="state"]', root);
      this.sayEl = $('[data-role="say"]', root);
      this.heardEl = $('[data-role="heard"]', root);
      this.tagEl = $('[data-role="tag"]', root);
      this.ressy = new Lines($(".hud__lines--ressy", root), COLORS.legend);
      this.user = new Lines($(".hud__lines--user", root), COLORS.accent);
      this.state = root.dataset.state || "listening";
      this.ressyText = this.sayEl.textContent.trim();
      this.statusText = "";
      this.userSource = null;
      this.open = !root.hidden;
      this.hideTimer = 0;
    }
    setState(state) {
      this.state = state;
      this.root.dataset.state = state;
      this.legend.textContent = STATE_LABELS[state] || "Ascolta";
      this.render();
    }
    say(text) {
      this.ressyText = text;
      this.statusText = "";
      this.render();
    }
    status(text) {
      this.statusText = text;
      this.render();
    }
    heard(text, final = false) {
      let shown = clipText(text, 160);
      if (final && text && text !== "Non ho sentito niente.") shown = `«${shown}»`;
      this.heardEl.textContent = shown;
      this.tagEl.hidden = !(final && text);
    }
    render() {
      const thinking = this.state === "thinking";
      let text;
      let dim;
      if (thinking && this.statusText) {
        text = this.statusText;
        dim = true;
      } else if (this.ressyText) {
        text = this.ressyText;
        dim = !(this.state === "speaking" || thinking);
      } else {
        text = this.statusText;
        dim = true;
      }
      this.sayEl.textContent = clipText(text, 230);
      this.sayEl.classList.toggle("is-dim", dim);
    }
    reveal() {
      clearTimeout(this.hideTimer);
      this.open = true;
      this.root.hidden = false;
      void this.root.offsetWidth;
      this.root.classList.add("is-open");
      this.ressy.values.fill(0);
      this.user.values.fill(0);
      this.ressy.resize();
      this.user.resize();
      Loop.wake();
    }
    conceal(focusTarget, linger = 0) {
      this.open = false;
      if (focusTarget && this.root.contains(document.activeElement)) focusTarget.focus({ preventScroll: true });
      clearTimeout(this.hideTimer);
      const close = () => {
        if (this.open) return;
        this.root.classList.remove("is-open");
        this.hideTimer = setTimeout(() => {
          if (!this.open) this.root.hidden = true;
        }, 190);
      };
      if (linger > 0) this.hideTimer = setTimeout(close, linger);
      else close();
    }
    voiceBars() {
      if (!this.bars) this.bars = $$(".mark__bar", this.root);
      const speaking = this.root.dataset.state === "speaking";
      const v = this.ressy.values;
      this.bars.forEach((bar, i) => {
        if (!speaking) {
          bar.style.setProperty("--v", "1");
          return;
        }
        const k = Math.min(v.length - 1, Math.floor(v.length * (0.1 + i * 0.2)));
        bar.style.setProperty("--v", Math.max(0, Math.min(1, v[k] || 0)).toFixed(3));
      });
    }
    tick(t, dt) {
      const ressy = Voice.bandsFor(this.owner, t);
      const user = this.userSource ? this.userSource() : null;
      const a = this.ressy.feed(ressy || ZERO, dt);
      this.voiceBars();
      const b = this.user.feed(user || ZERO, dt);
      return a || b || Boolean(ressy) || Boolean(user);
    }
  }
  const announcer = $('[data-role="announcer"]');
  function announce(text) {
    if (!announcer) return;
    announcer.textContent = "";
    setTimeout(() => {
      announcer.textContent = text;
    }, 60);
  }
  const boardNote = $('[data-role="board-note"]');
  const note = (text) => {
    if (boardNote) boardNote.textContent = text;
  };
  function setToggle(btn, on) {
    btn.setAttribute("aria-pressed", String(on));
    const state = $(".toggle__state", btn);
    if (state) state.textContent = on ? state.dataset.on : state.dataset.off;
  }
  const NOTES = {
    tap: "Tienilo premuto un po’ di più: un tocco veloce scrive solo la lettera, come sempre.",
    short: "Parla mentre tieni premuto il tasto e lascialo quando hai finito.",
    woke: "Nella demo Ressy si sveglia sempre e le richieste sono esempi: la pagina non trascrive niente. Tieni premuto K per il prossimo comando.",
    asleep: "Ressy è tornata a dormire. Tieni premuto K per svegliarla di nuovo.",
    noVoice: "Questo browser non ha una voce italiana: le risposte di Ressy restano scritte.",
    soundOff: "Audio spento: niente voce né suoni, le risposte restano scritte.",
    micOn: "Microfono acceso: le linee viola seguono la tua voce mentre Ressy ascolta. L’audio resta nel browser: la pagina non registra e non trascrive niente.",
    micOff: "Microfono spento.",
    micDenied: "Il browser non ha dato il permesso per il microfono. La demo funziona lo stesso, senza le tue linee.",
    micMissing: "Non trovo un microfono. La demo funziona lo stesso, senza le tue linee.",
    micUnsupported: "Questo browser non permette di usare il microfono su questa pagina. La demo funziona lo stesso.",
    micEnded: "Il microfono si è scollegato."
  };
  const TURNS = [
    { heard: "Apri Spotify", tool: "open_app", work: 900, reply: "Fatto, Spotify è aperto." },
    { heard: "Scrivi a Marco su Discord che arrivo tra dieci minuti", tool: "send_discord_message", work: 2e3, reply: "Fatto: ho scritto a Marco «arrivo tra dieci minuti»." },
    { heard: "Ricordami alle sei di chiamare la mamma", tool: "reminder", work: 700, reply: "Va bene: alle 18 ti ricordo di chiamare la mamma." },
    { heard: "Grazie, è tutto.", sleep: true }
  ];
  function heroDemo() {
    const talkKey = $("#talk-key");
    const hudRoot = $("#hud-hero");
    const board = $(".board");
    if (!talkKey || !hudRoot || !board) return;
    const hud = new HudView(hudRoot, "hero");
    const leds = $$(".leds li[data-led]");
    const keyEls = new Map($$(".key[data-code]", board).filter((el) => el !== talkKey).map((el) => [el.dataset.code, el]));
    let boardVisible = true;
    const demo = {
      state: "asleep",
      awake: false,
      holding: false,
      gen: 0,
      turn: 0,
      downBy: new Set(),
      pressAt: 0,
      holdAt: 0,
      holdTimer: 0,
      sleepTimer: 0,
      explained: false,
      voiceNoted: false,
      setState(state) {
        this.state = state;
        hud.setState(state);
        const led = state === "hearing" ? "listening" : state;
        for (const li of leds) {
          const on = li.dataset.led === led;
          li.classList.toggle("is-on", on);
          if (on) li.setAttribute("aria-current", "true");
          else li.removeAttribute("aria-current");
        }
        Loop.wake();
      },
      press(source) {
        AudioOut.ensure();
        const first = this.downBy.size === 0;
        this.downBy.add(source);
        if (!first) return;
        talkKey.classList.add("is-down");
        this.pressAt = now();
        clearTimeout(this.holdTimer);
        this.holdTimer = setTimeout(() => this.hold(), HOLD_MS);
      },
      release(source) {
        if (!this.downBy.delete(source) || this.downBy.size) return;
        talkKey.classList.remove("is-down");
        AudioOut.ensure();
        Voice.unlock();
        clearTimeout(this.holdTimer);
        if (!this.holding) {
          note(NOTES.tap);
          return;
        }
        this.holding = false;
        if (now() - this.holdAt < MIN_TALK_MS) {
          this.setState(this.awake ? "listening" : "asleep");
          if (this.awake) {
            hud.heard("");
            this.armSleep();
          }
          note(NOTES.short);
          return;
        }
        this.setState("thinking");
        this.converse(this.gen);
      },
      hold() {
        this.holding = true;
        this.holdAt = now();
        this.clearSleep();
        if (Voice.speaking("hero") || this.state === "speaking") Voice.cancel("hero");
        this.gen++;
        Cues.play("thock");
        this.setState("hearing");
        if (this.awake) hud.heard("…");
      },
      async converse(gen) {
        await wait(this.awake ? 600 : 650);
        if (gen !== this.gen) return;
        if (!this.awake) {
          await this.wakeUp();
          return;
        }
        const turn = TURNS[this.turn % TURNS.length];
        this.turn++;
        hud.heard(turn.heard, true);
        if (turn.sleep) {
          await this.say(farewell());
          if (gen !== this.gen) return;
          this.sleepNow(false);
          return;
        }
        this.setState("thinking");
        hud.status("");
        await wait(450);
        if (gen !== this.gen) return;
        hud.status(TOOL_STATUS[turn.tool] || "…");
        await wait(turn.work);
        if (gen !== this.gen) return;
        hud.status("");
        await this.say(turn.reply);
        if (gen !== this.gen) return;
        this.resumeIdle();
      },
      async wakeUp() {
        this.awake = true;
        this.gen++;
        const gen = this.gen;
        this.turn = 0;
        hud.reveal();
        Cues.play("wake");
        hud.heard("");
        if (!this.explained) {
          this.explained = true;
          note(NOTES.woke);
        }
        await this.say(greeting());
        if (gen !== this.gen) return;
        this.resumeIdle();
      },
      async say(text) {
        hud.say(text);
        this.setState("speaking");
        announce(`Ressy: ${text}`);
        if (prefs.sound && Voice.synth && !Voice.available && !this.voiceNoted) {
          this.voiceNoted = true;
          note(NOTES.noVoice);
        }
        await Voice.speak(text, "hero");
        await wait(ECHO_MS);
      },
      resumeIdle() {
        if (this.holding) return;
        if (this.awake) {
          this.setState("listening");
          hud.status("");
          this.armSleep();
        } else {
          this.setState("asleep");
        }
      },
      sleepNow(cue = true) {
        if (!this.awake) return;
        this.awake = false;
        this.gen++;
        Voice.cancel("hero");
        hud.status("");
        this.setState(this.holding ? "hearing" : "asleep");
        hud.conceal(talkKey, this.holding ? 0 : 620);
        this.clearSleep();
        if (cue) Cues.play("sleep");
        note(NOTES.asleep);
        announce("Ressy dorme.");
      },
      armSleep() {
        this.clearSleep();
        this.sleepTimer = setTimeout(() => {
          if (this.awake && this.state === "listening" && !this.holding) this.sleepNow(true);
        }, AUTO_SLEEP_MS);
      },
      clearSleep() {
        clearTimeout(this.sleepTimer);
      },
      userSource: () => {
        if (!Mic.on) return null;
        if (demo.state === "hearing" || demo.awake && demo.state === "listening") return Mic.bands();
        return null;
      }
    };
    hud.userSource = demo.userSource;
    Loop.add((t, dt) => hud.open ? hud.tick(t, dt) : false);
    talkKey.addEventListener("pointerdown", (e) => {
      if (e.pointerType === "mouse" && e.button !== 0) return;
      e.preventDefault();
      try {
        talkKey.setPointerCapture(e.pointerId);
      } catch (err) {
      }
      demo.press("pointer");
    });
    const pointerUp = () => demo.release("pointer");
    talkKey.addEventListener("pointerup", pointerUp);
    talkKey.addEventListener("pointercancel", pointerUp);
    talkKey.addEventListener("lostpointercapture", pointerUp);
    talkKey.addEventListener("contextmenu", (e) => e.preventDefault());
    talkKey.addEventListener("keydown", (e) => {
      if (e.key !== " " && e.key !== "Enter") return;
      e.preventDefault();
      if (!e.repeat) demo.press("key");
    });
    talkKey.addEventListener("keyup", (e) => {
      if (e.key !== " " && e.key !== "Enter") return;
      e.preventDefault();
      demo.release("key");
    });
    if ("IntersectionObserver" in window) {
      new IntersectionObserver((entries) => {
        for (const entry of entries) boardVisible = entry.isIntersecting;
      }, { threshold: 0.15 }).observe(board);
    }
    const editable = (el) => el instanceof Element && Boolean(el.closest('input, textarea, select, [contenteditable]:not([contenteditable="false"])'));
    window.addEventListener("keydown", (e) => {
      if (e.defaultPrevented || editable(e.target)) return;
      const key = (e.key || "").toLowerCase();
      if (key === "k") {
        if (e.ctrlKey || e.altKey || e.metaKey || !boardVisible) return;
        e.preventDefault();
        if (!e.repeat) demo.press("kbd");
        return;
      }
      if (!boardVisible || e.repeat) return;
      const el = keyEls.get(e.code);
      if (el) el.classList.add("is-down");
    });
    window.addEventListener("keyup", (e) => {
      if ((e.key || "").toLowerCase() === "k" || e.code === "KeyK") demo.release("kbd");
      const el = keyEls.get(e.code);
      if (el) el.classList.remove("is-down");
    });
    const releaseAll = () => {
      demo.release("kbd");
      demo.release("key");
      for (const el of keyEls.values()) el.classList.remove("is-down");
    };
    window.addEventListener("blur", releaseAll);
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) releaseAll();
    });
    const esc = $('[data-action="sleep"]', hudRoot);
    if (esc) esc.addEventListener("click", () => demo.sleepNow(true));
    const soundBtn = $('[data-toggle="sound"]');
    if (soundBtn) {
      soundBtn.addEventListener("click", () => {
        prefs.sound = soundBtn.getAttribute("aria-pressed") !== "true";
        setToggle(soundBtn, prefs.sound);
        if (prefs.sound) {
          AudioOut.ensure();
          note("");
        } else {
          Voice.cancel();
          note(NOTES.soundOff);
        }
      });
    }
    const micBtn = $('[data-toggle="mic"]');
    if (micBtn) {
      Mic.onEnded = () => {
        setToggle(micBtn, false);
        note(NOTES.micEnded);
      };
      micBtn.addEventListener("click", async () => {
        if (micBtn.getAttribute("aria-busy") === "true") return;
        if (Mic.on) {
          Mic.stop();
          setToggle(micBtn, false);
          note(NOTES.micOff);
          return;
        }
        micBtn.setAttribute("aria-busy", "true");
        try {
          await Mic.start();
          setToggle(micBtn, true);
          note(NOTES.micOn);
        } catch (err) {
          Mic.stop();
          setToggle(micBtn, false);
          Cues.play("error");
          const name = err && err.name;
          if (name === "Unsupported") note(NOTES.micUnsupported);
          else if (name === "NotAllowedError" || name === "SecurityError") note(NOTES.micDenied);
          else note(NOTES.micMissing);
        } finally {
          micBtn.removeAttribute("aria-busy");
        }
      });
    }
  }
  const EXAMPLES = {
    app: {
      heard: "Apri Spotify",
      tool: "open_app",
      work: 900,
      reply: "Fatto, Spotify è aperto.",
      how: "Cerca il programma nel menu Start, con il nome che ha sul tuo Windows, e lo avvia come un clic su Start. Vale anche per le app del Microsoft Store."
    },
    discord: {
      heard: "Scrivi a Marco su Discord che arrivo tra dieci minuti",
      tool: "send_discord_message",
      work: 2e3,
      reply: "Fatto: ho scritto a Marco «arrivo tra dieci minuti».",
      how: "Usa l’app di Discord come faresti tu: apre la chat con Ctrl+K, controlla dal titolo della finestra che sia quella giusta, poi scrive e invia. Se non è sicura della chat, non manda niente."
    },
    youtube: {
      heard: "Metti su YouTube un po’ di musica lo-fi",
      tool: "play_youtube",
      work: 1400,
      reply: "Parte su YouTube il primo risultato per «musica lo-fi».",
      how: "Cerca su YouTube e apre il primo video nel tuo browser. Se YouTube non mostra i risultati, apre la pagina di ricerca e il video lo scegli tu."
    },
    music: {
      heard: "Metti la prossima canzone",
      tool: "media_control",
      work: 500,
      reply: "Ecco la prossima.",
      how: "Usa i tasti multimediali di Windows, quindi funziona con Spotify, YouTube e quasi tutti i lettori. Con «alza il volume» o «volume al 30» regola anche l’audio del PC."
    },
    screenshot: {
      heard: "Fammi uno screenshot",
      tool: "take_screenshot",
      work: 700,
      reply: "Fatto, l’ho salvato in Immagini, nella cartella Ressy.",
      how: "Cattura tutti gli schermi e salva il file in Immagini\\Ressy. Se lo chiedi da Telegram o da Discord, l’immagine te la manda in chat."
    },
    reminder: {
      heard: "Ricordami alle sei di chiamare la mamma",
      tool: "reminder",
      work: 700,
      reply: "Va bene: alle 18 ti ricordo di chiamare la mamma.",
      how: "I promemoria restano salvati anche se riavvii il PC. All’ora giusta Ressy te lo dice a voce; se l’hai chiesto dal telefono, te lo scrive anche in chat."
    },
    web: {
      heard: "Che tempo fa domani a Milano?",
      tool: "web_answer",
      work: 2200,
      reply: "Domani a Milano sole al mattino e qualche nuvola la sera, con una massima di 14 gradi.",
      how: "Per quello che cambia, come meteo, notizie e risultati, cerca sul web con Groq e ti risponde in poche frasi, senza aprire il browser."
    },
    power: {
      heard: "Spegni il PC tra un minuto",
      tool: "pc_power",
      work: 600,
      reply: "Spengo il PC tra 60 secondi. Se cambi idea, dimmi di annullare lo spegnimento.",
      how: "Blocca, sospende, spegne o riavvia il PC. Lo spegnimento parte dopo un minuto, così hai il tempo di dirle «annulla lo spegnimento»."
    },
    close: {
      heard: "Chiudi Word",
      tool: "close_app",
      work: 1800,
      reply: "Word ti sta chiedendo se salvare, quindi l’ho lasciato aperto. Se vuoi lo chiudo lo stesso, ma perdi le modifiche.",
      how: "Chiude le finestre come faresti tu, così il programma può chiederti di salvare. Lo chiude a forza solo se glielo dici."
    },
    type: {
      heard: "Scrivi: ci vediamo alle otto davanti al cinema",
      tool: "type_text",
      work: 900,
      reply: "Fatto, l’ho scritto nella finestra aperta.",
      how: "Scrive nella finestra che hai davanti, come se usassi la tastiera: una mail, una chat, un documento."
    }
  };
  function examples() {
    const root = $("#hud-tasks");
    if (!root) return;
    const hud = new HudView(root, "tasks");
    const how = $('[data-role="how"]');
    const keys = $$(".nkey[data-example]");
    let gen = 0;
    hud.say(`${dayPart()}! Cosa posso fare per te?`);
    hud.setState("listening");
    Loop.add((t, dt) => hud.tick(t, dt));
    async function run(name) {
      const ex = EXAMPLES[name];
      if (!ex) return;
      gen++;
      const g = gen;
      for (const key of keys) key.setAttribute("aria-pressed", String(key.dataset.example === name));
      if (how) how.textContent = ex.how;
      Voice.cancel("tasks");
      hud.heard("…");
      hud.status("");
      hud.setState("thinking");
      await wait(450);
      if (g !== gen) return;
      hud.heard(ex.heard, true);
      await wait(350);
      if (g !== gen) return;
      hud.status(TOOL_STATUS[ex.tool] || "…");
      await wait(ex.work);
      if (g !== gen) return;
      hud.status("");
      hud.say(ex.reply);
      hud.setState("speaking");
      await Voice.speak(ex.reply, "tasks");
      if (g !== gen) return;
      await wait(ECHO_MS);
      if (g !== gen) return;
      hud.setState("listening");
      hud.status("");
    }
    for (const key of keys) {
      key.addEventListener("click", () => {
        AudioOut.ensure();
        Voice.unlock();
        run(key.dataset.example);
      });
    }
  }
  const PC_NAME = "PC di casa";
  const REMOTE = {
    quit: `🔴 Offline: Ressy è stata chiusa sul PC «${PC_NAME}».
I comandi non verranno eseguiti finché non la riavvii.`,
    offline: `🔴 Offline: Ressy non è attiva sul tuo PC «${PC_NAME}» (ultimo contatto: pochi secondi fa).
Il comando NON verrà eseguito. Avvia Ressy sul PC e riprova.`,
    online: `🟢 Online: Ressy è di nuovo online sul PC «${PC_NAME}», puoi darle comandi.`
  };
  function remote() {
    const btn = $('[data-action="power"]');
    const label = btn && $("[data-label]", btn);
    const pcBoard = $('[data-role="pc-board"]');
    const presence = $('[data-role="presence"]');
    const chat = $('[data-role="chat"]');
    if (!btn || !label || !pcBoard || !presence || !chat) return;
    let online = true;
    let timers = [];
    const later = (ms, fn) => timers.push(setTimeout(fn, ms));
    const add = (who, text) => {
      const li = document.createElement("li");
      li.className = `msg msg--${who} is-demo is-new`;
      li.textContent = text;
      chat.appendChild(li);
    };
    btn.addEventListener("click", () => {
      timers.forEach(clearTimeout);
      timers = [];
      online = !online;
      pcBoard.dataset.online = String(online);
      presence.textContent = online ? "Online" : "Offline";
      label.textContent = online ? "Spegni il PC" : "Riaccendi il PC";
      if (!online) {
        for (const li of $$(".is-demo", chat)) li.remove();
        later(500, () => add("bot", REMOTE.quit));
        later(1900, () => add("me", "apri spotify"));
        later(2800, () => add("bot", REMOTE.offline));
      } else {
        later(700, () => add("bot", REMOTE.online));
      }
    });
  }
  function trimLegends() {
    const frame = $(".board__frame");
    if (!frame || !("ResizeObserver" in window)) return;
    const keys = $$(".keys .key", frame).filter((key) => key.id !== "talk-key");
    const fit = () => {
      const box = frame.getBoundingClientRect();
      for (const key of keys) {
        const cut = $$(".lg, .enter__label, .enter__sub", key).some((mark) => {
          const r = mark.getBoundingClientRect();
          return r.width > 0 && (r.left < box.left + 1 || r.right > box.right - 1);
        });
        key.classList.toggle("is-cut", cut);
        if (key.tagName === "A") {
          if (cut) {
            key.setAttribute("tabindex", "-1");
            key.setAttribute("aria-hidden", "true");
          } else {
            key.removeAttribute("tabindex");
            key.removeAttribute("aria-hidden");
          }
        }
      }
    };
    new ResizeObserver(fit).observe(frame);
    if (document.fonts) document.fonts.ready.then(fit);
  }
  const motionOK = document.documentElement.classList.contains("motion");
  const calm = document.documentElement.classList.contains("calm");
  function marks() {
    const brands = $$(".topbar .mark, .footer .mark");
    if (!brands.length) return;
    const wave = (m) => {
      m.classList.remove("is-wave");
      void m.getBoundingClientRect();
      m.classList.add("is-wave");
      setTimeout(() => m.classList.remove("is-wave"), 1100);
    };
    const schedule = () => {
      setTimeout(() => {
        if (!document.hidden && !calm) {
          for (const m of brands) {
            const r = m.getBoundingClientRect();
            if (r.bottom > 0 && r.top < innerHeight) wave(m);
          }
        }
        schedule();
      }, 7e3 + Math.random() * 6e3);
    };
    if (motionOK) schedule();
  }
  function reveals() {
    const index = (els) => els.forEach((el, i) => el.style.setProperty("--i", i));
    index($$(".topbar .fkey"));
    index($$(".hero .facts li"));
    index($$(".pc__board .pkey"));
    if (!motionOK || !("IntersectionObserver" in window)) return;
    const mark = (els, kind) => {
      index(els);
      for (const el of els) el.dataset.reveal = kind || "";
    };
    for (const head of $$(".sheet__head")) {
      const h2 = $("h2", head);
      const spans = $$(":scope > span", h2);
      mark(spans.length ? spans : [h2], "rise");
      const p = $("p", head);
      if (p) {
        p.dataset.reveal = "";
        p.style.setProperty("--i", spans.length + 1);
      }
    }
    mark($$(".novelties .nkey"));
    mark($$(".example > *"));
    mark($$(".remote > *"));
    mark($$(".chat__log > .msg"), "type");
    mark($$(".pairing__code .ckey"), "type");
    mark($$(".pairing__text"));
    mark($$(".specs > div"));
    mark($$(".steps .step"));
    mark($$(".smartscreen"));
    mark($$(".faq details"));
    mark($$(".close__copy > *"), "rise");
    mark($$(".big-enter"), "pop");
    mark($$(".footer__inner > *"));
    const io = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        entry.target.classList.add("is-in");
        io.unobserve(entry.target);
      }
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.12 });
    for (const el of $$("[data-reveal]")) io.observe(el);
  }
  Voice.init();
  trimLegends();
  reveals();
  marks();
  heroDemo();
  examples();
  remote();
  window.addEventListener("pagehide", () => {
    Voice.cancel();
    Mic.stop();
  });
})();
