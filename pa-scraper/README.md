# PA Scraper — warsztat analityka

Lokalna aplikacja do użytku własnego: **React (Vite)** + **Python (FastAPI)**.

Dwie funkcje:

1. **Wątek forum PortalAnaliz** — logowanie własnymi credentialami do phpBB
   i pobranie wszystkich postów z wątku (z paginacją), np.
   `https://portalanaliz.pl/forum/viewtopic.php?f=3&t=496`.
   Eksport całości do Markdown jednym kliknięciem.
2. **BiznesRadar** — pobranie rachunku zysków i strat po tickerze
   (np. `MBR` → `https://www.biznesradar.pl/raporty-finansowe-rachunek-zyskow-i-strat/MBR`),
   dane kwartalne lub roczne, wyświetlone jako tabela.

## Struktura

```
pa-scraper/
├── backend/
│   ├── main.py                 # FastAPI: endpointy /api/*
│   ├── forum_scraper.py        # logowanie phpBB + parser postów (przetestowany na realnym HTML PA)
│   ├── biznesradar_scraper.py  # parser tabeli report-table
│   └── requirements.txt
└── frontend/
    ├── package.json / vite.config.js / index.html
    └── src/ (App.jsx, styles.css, main.jsx)
```

## Uruchomienie

### 1. Backend (Python 3.10+)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 2. Frontend (Node 18+)

```bash
cd frontend
npm install
npm run dev
```

Otwórz `http://localhost:5173`. Vite proxuje `/api` na backend (port 8000).

## API (można używać też bez frontendu)

| Endpoint | Opis |
|---|---|
| `POST /api/forum/login` | `{username, password}` → `{session_token}` |
| `POST /api/forum/scrape` | `{session_token?, topic_url, all_pages}` → posty JSON |
| `GET /api/forum/export/markdown` | ostatni pobrany wątek jako Markdown |
| `GET /api/biznesradar/{ticker}?quarterly=true` | rachunek zysków i strat JSON |

Przykład bez frontendu:

```bash
curl -X POST localhost:8000/api/forum/scrape \
  -H 'Content-Type: application/json' \
  -d '{"topic_url": "https://portalanaliz.pl/forum/viewtopic.php?f=3&t=496", "all_pages": true}'

curl localhost:8000/api/biznesradar/MBR
```

## Bezpieczeństwo i dobre praktyki

- **Credentiale nie są nigdzie zapisywane** — żyją tylko w pamięci procesu backendu
  (sesja `requests`), znikają po restarcie.
- Backend robi **1,5 s przerwy między requestami** do forum — nie zmniejszaj tego;
  szanuj serwer, z którego korzystasz.
- Pobieraj wyłącznie treści, do których masz legalny dostęp jako zalogowany
  użytkownik, do użytku własnego. Sprawdź regulamin PortalAnaliz i BiznesRadar —
  odpowiedzialność za sposób użycia narzędzia jest po Twojej stronie.
- Aplikacja jest lokalna (localhost). Nie wystawiaj backendu publicznie —
  endpoint logowania przyjmuje hasła plaintextem po HTTP.

## Uwagi techniczne

- Parser forum rozpoznaje: `div.post.has-profile` → autor (`a.username-coloured`),
  data (`time[datetime]`), treść (`div.content`). Zweryfikowany na zapisanych
  stronach wątku „Portfel IKE - OBS" (50/50 postów na stronę).
- URL typu `viewtopic.php?p=115348#p115348` (link do konkretnego posta) też działa —
  backend odczytuje `t` wątku z tagu canonical i pobiera całość.
- Parser BiznesRadar szuka `table.report-table`; jeśli serwis zmieni strukturę,
  poprawki robi się w jednym miejscu (`biznesradar_scraper.py`).
- BiznesRadar może blokować automatyczne pobieranie przy dużej częstotliwości —
  używaj punktowo.
