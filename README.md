# Oistros

The philosophical AI-gadfly. Reads ancient Greek and Roman texts, observes current news, and writes philosophical commentary — all locally, using a small open-source LLM through Ollama.

Named after the gadfly (οἶστρος) that Socrates compared himself to — a persistent sting that keeps the city thinking.

## What it does

Every 30 minutes (configurable), Oistros:

1. **Reads** a random passage from its catalog of 30+ classical works (Homer, Plato, Aristotle, the Stoics, and more) via the Perseus/Scaife digital library
2. **Scans** current news headlines from RSS feeds (Reuters, AP, BBC, etc.)
3. **Thinks** — sends both to a local LLM (Qwen3 0.6B by default) with instructions to find the "structural rhyme between ages"
4. **Writes** a short philosophical commentary (aphorism or micro-essay) as a timestamped markdown file

Everything runs locally. No cloud APIs, no subscriptions. Works on a Raspberry Pi.

## Install

**One-line install (Linux):**

```bash
git clone https://github.com/dogacol/oistros.git && cd oistros && bash install.sh
```

This will:
- Find or install Python 3.10+
- Create a virtual environment and install the package
- Install Ollama (if not present)
- Pull the Qwen3 0.6B model (~400MB)

**Manual install:**

```bash
git clone https://github.com/dogacol/oistros.git
cd oistros
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Then install [Ollama](https://ollama.com) separately and pull a model:

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3:0.6b
```

## Usage

Activate the virtualenv first:

```bash
source .venv/bin/activate
```

Then use the `oistros` command:

```
oistros              Run as daemon (cycle every 30 min)
oistros run          Run one full cycle
oistros test         Test passage fetching + news scanning (no LLM needed)
oistros read         Fetch and display a random ancient passage
oistros scan         Scan and display current news headlines
oistros log          Show recent outputs
```

**Flags:**

```
--config PATH        Use a custom config file (default: config.yaml)
--verbose            Enable debug logging
--version            Show version
```

### Quick test (no Ollama needed)

```bash
oistros test
```

This fetches a passage from Perseus/Scaife and scans news feeds to verify everything works, without calling the LLM.

### Run one cycle

```bash
ollama serve &       # start Ollama if not already running
oistros run
```

Output is written to `output/YYYY-MM-DD_HHMM.md`.

### Run as a systemd service

The installer generates an `oistros.service` file. To run Oistros as a background service:

```bash
sudo cp oistros.service /etc/systemd/system/
sudo systemctl enable --now oistros
```

## Configuration

Edit `config.yaml`:

```yaml
interval_minutes: 30          # Daemon cycle interval

selection_mode: random        # "random" or "threaded" (follows recent themes)
memory_context_size: 5        # Recent entries for context

thinker:
  model: "qwen3:0.6b"        # Any Ollama model
  ollama_url: "http://localhost:11434"
  thinking_mode: true         # Chain-of-thought reasoning
  temperature: 0.7
  max_tokens: 1024

scanner:
  max_topics: 5
  # Custom RSS feeds:
  # feeds:
  #   - name: "Reuters World"
  #     url: "https://feeds.reuters.com/Reuters/worldNews"
```

You can use any model available in Ollama. Smaller models (0.5B–3B) work well on a Raspberry Pi; larger ones produce richer output.

## Text catalog

Oistros includes a curated catalog of 30+ works spanning a millennium of ancient thought:

| | Works |
|---|---|
| **Epic** | Homer (*Iliad*, *Odyssey*), Hesiod (*Works and Days*), Pindar (*Olympian Odes*) |
| **Pre-Socratics** | Heraclitus, Parmenides, Empedocles (fragments) |
| **Tragedy** | Aeschylus (*Agamemnon*, *Prometheus Bound*), Sophocles (*Antigone*, *Oedipus Tyrannus*), Euripides (*Bacchae*, *Medea*) |
| **History** | Herodotus (*Histories*), Thucydides (*Peloponnesian War*) |
| **Plato** | *Apology*, *Republic*, *Symposium*, *Phaedrus*, *Phaedo*, *Timaeus* |
| **Aristotle** | *Nicomachean Ethics*, *Politics*, *Poetics*, *Metaphysics* |
| **Hellenistic & Roman** | Epictetus (*Discourses*, *Enchiridion*), Marcus Aurelius (*Meditations*), Lucretius (*De Rerum Natura*), Plotinus (*Enneads*), Diogenes Laertius (*Lives*) |

Texts are fetched from the [Perseus Digital Library](https://scaife.perseus.org) via the Scaife Viewer API, with local caching. Pre-Socratic fragments and Marcus Aurelius's *Meditations* are bundled locally.

## Project structure

```
oistros/
├── cli.py          Command-line interface and cycle orchestration
├── reader.py       Passage fetching (Scaife/Perseus API + local fragments)
├── scanner.py      RSS news scanning and deduplication
├── thinker.py      Ollama LLM interface and prompt construction
├── memory.py       JSONL-based history and theme tracking
├── writer.py       Markdown output formatting
└── data/
    └── catalog.json    Text catalog with CTS URNs
```

## Requirements

- **Linux** (including Raspberry Pi / ARM)
- **Python 3.10+**
- **Ollama** with any pulled model
- Internet connection (for fetching passages and news)

## License

MIT
