# 🕸️ Local Knowledge-Base Scraper & Builder

Create a **structured, LLM-ready knowledge base** from any public website **entirely on your local machine**.  
No chatbot is shipped here—the output JSON is meant to be dropped into *your* bot or voice-agent project.

![Streamlit](https://img.shields.io/badge/Built_with-Streamlit-fd4a02?logo=streamlit&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

---

## ✨ Key Features

|                                   | Description |
|-----------------------------------|-------------|
| **Single-domain crawler**         | Scrapes every internal page (depth-limited) and cleans the HTML with *Trafilatura*. |
| **File uploader**                 | Parses PDF / DOCX / standalone HTML. |
| **Two-stage LLM pipeline**        | 1️⃣ *Per-page* JSON extraction → 2️⃣ *Cross-doc* synthesis into a single knowledge-base JSON. |
| **Fully local execution**         | Only outbound traffic is the OpenAI API call (if you enable it). |
| **Modular codebase**              | Swap crawlers, parsers or LLM prompts easily. |

---

## 🗂️ Repository Layout

| Path | Role |
|------|------|
| `streamlit_app.py`         | Streamlit UI & orchestration |
| `scraper.py`               | Breadth-first crawler & cleaner |
| `document_parser.py`       | PDF/DOCX/HTML → plain text |
| `ai_processor.py`          | **Stage 1** – per-page extraction prompt |
| `ai_batch_processor.py`    | Helper to loop Stage 1 over many docs |
| `content_combiner.py`      | **Stage 2** – combine all Stage 1 JSON into final KB |
| `openai_client.py`         | Thin wrapper around OpenAI Chat Completions API |

---

## 🚀 Quick Start

```bash
git clone https://github.com/your-username/local-kb-scraper.git
cd local-kb-scraper

python -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env              # add your OPENAI_API_KEY
streamlit run streamlit_app.py
```

Open your browser at **[http://localhost:8501](http://localhost:8501)**.

---

## 🖥️ Using the App

### 1. Collect Raw Content

| Option            | How                                                                                               |
| ----------------- | ------------------------------------------------------------------------------------------------- |
| **Scrape a site** | Paste one URL (e.g. `https://docs.example.com/guide/`) → choose *depth* & *page cap* → **Scrape** |
| **Upload files**  | Drag & drop PDFs, DOCXs or HTML files                                                             |

Raw text for every page/file lands in `data/raw/YYYY-MM-DD-HHMMSS/`.

---

### 2. Stage 1 — Per-page Processing

Click **"Run Stage 1 (per-page)"**.
Each raw text chunk is sent to the LLM with a prompt that extracts:

```json
{
  "title": "...",
  "sections": [...],
  "metadata": {...}
}
```

Outputs are stored next to the raw text as
`data/stage1/{original_name}_YYYYMMDD_HHMMSS.json`.

---

### 3. Stage 2 — Build the Knowledge Base

Press **"Combine & Build KB"**.
`content_combiner.py` ingests all Stage 1 JSON, deduplicates topics, and produces **one** file:

```
data/knowledgebase/final_agent_YYYYMMDD_HHMMSS.json
```

This JSON already contains:

* *Agent system prompt* (for chat/voice bots)
* Fully voice-optimised copy (numbers spelled out, pronunciations, etc.)
* Section hierarchy and metadata ready for RAG indexing

---

## 📤 What to Do with the Output

The final JSON can be:

* Indexed into a vector DB (Chroma, Weaviate, Pinecone…) for retrieval-augmented generation.
* Fed straight into a chatbot as a system prompt.
* Read aloud by a TTS engine for an IVR or voice assistant.

---

## ⚙️ Configuration

| Env / Constant  | Default        | Meaning                          |
| --------------- | -------------- | -------------------------------- |
| `MAX_PAGES`     | `100`          | Hard upper bound during crawling |
| `MAX_UPLOAD_MB` | `25`           | Reject larger files              |
| `OPENAI_MODEL`  | `gpt-4o-mini`  | Stage 1 & 2 model                |
| `CHUNK_SIZE`    | `3_000` tokens | Token window per page            |

Edit the constants at the top of each module or override in `.env`.

---

## 🔒 Pragmatic Security Notes

* **Runs on localhost** – your browser *and* backend stay on your PC.
* **SSRF guard** – crawler blocks private IPs by default.
* **Upload cap & MIME check** – mitigates "zip-bomb" PDFs.
* **Prompt delimiting** – user text wrapped in `<<BEGIN_CONTENT>> / <<END_CONTENT>>` to reduce prompt injection risk.

---

## 🤝 Contributing

1. Fork 🔀 and create a feature branch 🌿
2. `pre-commit install` to auto-format with *black* & *isort*
3. Open a PR 🚀

---

## 📄 License

[MIT](LICENSE) – free for personal and commercial use.

---

## 🙏 Acknowledgements

* [Streamlit](https://streamlit.io) – instant UI
* [Trafilatura](https://github.com/adbar/trafilatura) – rock-solid text extraction
* [OpenAI](https://openai.com) – LLM magic
* Early TikTok testers for all the feedback!

---

## 🌟 Community & Support

**Skool Community:** Join our AI Freedom Finders community for support, discussions, and updates: https://www.skool.com/ai-freedom-finders

**TikTok:** Follow for AI tutorials, tips, and behind-the-scenes content: https://www.tiktok.com/@ai_entrepreneur_educator

Brought to you by [bramforth.ai](https://bramforth.ai)

Built with ❤️ for the AI community. Happy coding!
