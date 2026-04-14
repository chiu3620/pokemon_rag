# Pokemon Wiki RAG

A Retrieval-Augmented Generation (RAG) system for querying Pokemon knowledge in Traditional Chinese. It scrapes data from [52Poke Wiki](https://wiki.52poke.com/), processes and chunks it, builds hybrid search indexes (vector + BM25), and answers questions via LLM.

## Architecture

```text
Scrape (52Poke Wiki)
  → Clean & convert to Traditional Chinese
    → Restructure & parse tables
      → Merge & enrich with generation info
        → Chunk text (~500 chars)
          → Build FAISS vector index (BAAI/bge-m3) + BM25 index
            → Hybrid retrieval + GPT-4o-mini for Q&A
```

## Project Structure

```
├── scripts/
│   ├── process/
│   │   ├── clean_data.py              # Remove noise fields and newlines
│   │   ├── convert_to_traditional.py  # Simplified → Traditional Chinese (OpenCC)
│   │   ├── json_restructured.py       # Restructure raw JSON using heading rules
│   │   ├── deal_table.py              # Parse complex tables (evolution, game data)
│   │   ├── merge_all_json.py          # Merge base + detail data into unified files
│   │   ├── update_generation.py       # Add generation metadata to each Pokemon
│   │   └── run_all.py                 # Run all processing steps in order
│   ├── rag/
│   │   ├── chunk.py                   # Split documents into semantic chunks
│   │   ├── rag_build.py               # Build FAISS vector embeddings
│   │   ├── bm25_build_local.py        # Build BM25 sparse index
│   │   ├── bm25_search_local.py       # BM25 search lookup
│   │   ├── rag_chat.py                # RAG chat interface (OpenAI)
│   │   ├── rag_chat_google.py         # RAG chat with hybrid retrieval & reranking
│   │   └── build_all.py               # Run chunk + index steps in order
│   └── utils/
│       ├── delete_key.py              # Batch remove keys from JSON files
│       └── json_field_inventory.py    # Analyze JSON field statistics → Excel
├── docs/                              # Planning notes (Chinese)
├── data/                              # All data files (not tracked in git)
│   ├── pokemon/                       # Per-Pokemon JSON files (Raw & Processed)
│   ├── ability/                       # Per-ability JSON files
│   ├── move/                          # Per-move JSON files
│   ├── chunk/                         # Chunked documents for RAG
│   ├── embeddings/                    # FAISS index, BM25 index, embeddings
│   └── images/                        # Pokemon images
└── output/                            # Intermediate processing results (not tracked)
```


## Data

The JSON data files are **not included** in this repository.

To obtain the raw Pokemon data, scrape it from the [52Poke Wiki](https://wiki.52poke.com/) using MediaWiki API, or use the dataset from [42arch/pokemon-dataset-zh](https://github.com/42arch/pokemon-dataset-zh/tree/main/data) as a starting point.

The final processed JSON files (`data/pokemon/{index}-{name}.json`, e.g. `0025-皮卡丘.json`) have this schema:

```jsonc
{
  "name": "...",                // Traditional Chinese name
  "index": "0025",              // National Pokédex number
  "name_en": "...",             // English name
  "name_jp": "...",             // Japanese name
  "generation": 1,              // Generation number
  "profile": "...",             // Long-form description text
  "forms": [                    // One entry per form (base, mega, gmax, regional, etc.)
    {
      "name": "...",
      "index": "0025",
      "is_mega": false,
      "is_gmax": false,
      "image": "0025-xxx.png",
      "types": ["..."],
      "genus": "...",
      "ability": [{"name": "...", "is_hidden": false}, {"name": "...", "is_hidden": true}],
      "experience": {"number": "...", "speed": "..."},
      "height": "...",
      "weight": "...",
      "gender_rate": {"male": "...", "female": "..."},
      "shape": "...",
      "color": "...",
      "catch_rate": {"number": "...", "rate": "..."},
      "egg_groups": ["...", "..."]
    }
  ],
  "evolution_data": { ... },    // Evolution chain data
  "base_stats": { ... },        // HP, Atk, Def, SpA, SpD, Spe per form
  "pokedex_info_anime": { ... },// Anime Pokédex entries
  "pokedex_info_game": { ... }, // Game Pokédex entries by version
  "name_etymology": "...",     // Name origin / etymology
  "in_game_data": "...",       // In-game encounter & acquisition info
  "moves_learned": "...",      // Moves learned by level-up
  "moves_machine": "..."       // Moves learned by TM/HM
}
```

## Setup

### Prerequisites

- Python 3.10+
- An OpenAI API key (for the chat interface)

### Install Dependencies

```bash
pip install requests beautifulsoup4 lxml opencc-python-reimplemented
pip install sentence-transformers faiss-cpu numpy rank-bm25 tqdm
pip install openai pandas openpyxl
```

### Build the Index

1. **Prepare data**: Place processed Pokemon JSON files under `data/full/` (see [Data](#data) for schema).

2. **Clean & process** (run in order):
   ```bash
   python scripts/process/run_all.py
   ```

3. **Chunk & index**:
   ```bash
   python scripts/rag/build_all.py
   ```

### Chat

```bash
python scripts/rag/rag_chat.py
```

Set your OpenAI API key via environment variable or `.env` file before running.

## License

This project is for educational and personal use only.

Pokémon is a trademark of Nintendo / Creatures Inc. / GAME FREAK Inc. This project is not affiliated with or endorsed by them.

Pokémon data is sourced from [52Poke Wiki](https://wiki.52poke.com/), which is licensed under [CC BY-NC-SA 2.5](https://creativecommons.org/licenses/by-nc-sa/2.5/). The data is **not redistributed** in this repository.
