import { useState } from 'react'

const API = '/api'

async function jsonFetch(url, opts) {
  const res = await fetch(url, opts)
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(body.detail || `Błąd HTTP ${res.status}`)
  return body
}

/* ------------------------------------------------------------- Forum tab */

function ForumTab() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [token, setToken] = useState(null)
  const [topicUrl, setTopicUrl] = useState(
    'https://portalanaliz.pl/forum/viewtopic.php?f=3&t=496',
  )
  const [allPages, setAllPages] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)

  const login = async () => {
    setBusy(true); setError(null)
    try {
      const data = await jsonFetch(`${API}/forum/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      })
      setToken(data.session_token)
    } catch (e) { setError(e.message) }
    setBusy(false)
  }

  const scrape = async () => {
    setBusy(true); setError(null); setResult(null)
    try {
      const data = await jsonFetch(`${API}/forum/scrape`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_token: token, topic_url: topicUrl, all_pages: allPages }),
      })
      setResult(data)
    } catch (e) { setError(e.message) }
    setBusy(false)
  }

  const downloadMarkdown = () => {
    window.open(`${API}/forum/export/markdown?session_token=${token ?? ''}`, '_blank')
  }

  return (
    <section>
      <div className="panel">
        <h2>1. Zaloguj się do forum</h2>
        <p className="hint">
          Dane logowania trafiają wyłącznie do Twojego lokalnego backendu i żyją tylko
          w pamięci sesji — nie są nigdzie zapisywane. Publiczne wątki można pobierać
          też bez logowania.
        </p>
        <div className="row">
          <label>Login
            <input value={username} onChange={e => setUsername(e.target.value)} autoComplete="username" />
          </label>
          <label>Hasło
            <input type="password" value={password} onChange={e => setPassword(e.target.value)} autoComplete="current-password" />
          </label>
          <button onClick={login} disabled={busy || !username || !password}>
            {token ? 'Zalogowano ✓' : 'Zaloguj'}
          </button>
        </div>
      </div>

      <div className="panel">
        <h2>2. Pobierz wątek</h2>
        <div className="row">
          <label className="grow">Adres wątku (viewtopic.php…)
            <input value={topicUrl} onChange={e => setTopicUrl(e.target.value)} />
          </label>
        </div>
        <div className="row">
          <label className="check">
            <input type="checkbox" checked={allPages} onChange={e => setAllPages(e.target.checked)} />
            wszystkie strony wątku
          </label>
          <button onClick={scrape} disabled={busy || !topicUrl}>
            {busy ? 'Pobieram…' : 'Pobierz posty'}
          </button>
          {result && <button className="ghost" onClick={downloadMarkdown}>Eksportuj do Markdown</button>}
        </div>
      </div>

      {error && <p className="error">{error}</p>}

      {result && (
        <div className="panel">
          <h2>{result.title || 'Wątek'}</h2>
          <p className="hint">
            Postów: {result.post_count} · stron: {result.pages_scraped}
          </p>
          <div className="posts">
            {result.posts.map(p => (
              <article key={p.post_id} className="post">
                <header>
                  <strong>{p.author}</strong>
                  <time>{p.datetime_iso?.slice(0, 16).replace('T', ' ')}</time>
                </header>
                <pre>{p.content_text}</pre>
              </article>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}

/* ------------------------------------------------------- BiznesRadar tab */

function fmt(n) {
  if (n === null || n === undefined) return '—'
  return n.toLocaleString('pl-PL')
}

function BiznesRadarTab() {
  const [ticker, setTicker] = useState('MBR')
  const [quarterly, setQuarterly] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [data, setData] = useState(null)

  const load = async () => {
    setBusy(true); setError(null); setData(null)
    try {
      const d = await jsonFetch(`${API}/biznesradar/${encodeURIComponent(ticker)}?quarterly=${quarterly}`)
      setData(d)
    } catch (e) { setError(e.message) }
    setBusy(false)
  }

  return (
    <section>
      <div className="panel">
        <h2>Rachunek zysków i strat (BiznesRadar)</h2>
        <div className="row">
          <label>Ticker
            <input value={ticker} onChange={e => setTicker(e.target.value.toUpperCase())} placeholder="np. MBR" />
          </label>
          <label className="check">
            <input type="checkbox" checked={quarterly} onChange={e => setQuarterly(e.target.checked)} />
            dane kwartalne
          </label>
          <button onClick={load} disabled={busy || !ticker}>
            {busy ? 'Pobieram…' : 'Pobierz raport'}
          </button>
        </div>
      </div>

      {error && <p className="error">{error}</p>}

      {data && (
        <div className="panel">
          <h2>{data.company}</h2>
          <p className="hint">
            Źródło: <a href={data.source_url} target="_blank" rel="noreferrer">{data.source_url}</a>
          </p>
          <div className="table-wrap">
            <table className="ledger">
              <thead>
                <tr>
                  <th>Pozycja</th>
                  {data.periods.map((p, i) => <th key={i}>{p}</th>)}
                </tr>
              </thead>
              <tbody>
                {data.rows.map((r, i) => (
                  <tr key={i}>
                    <td className="pos">{r.name}</td>
                    {r.values.map((v, j) => (
                      <td key={j} className={v.number < 0 ? 'neg' : ''}>
                        {v.number !== null ? fmt(v.number) : (v.raw || '—')}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  )
}

/* ------------------------------------------------------------------- App */

export default function App() {
  const [tab, setTab] = useState('forum')
  return (
    <div className="shell">
      <header className="masthead">
        <h1>Warsztat analityka</h1>
        <p>PortalAnaliz · BiznesRadar — scraper do użytku własnego</p>
        <nav>
          <button className={tab === 'forum' ? 'active' : ''} onClick={() => setTab('forum')}>
            Wątek forum
          </button>
          <button className={tab === 'br' ? 'active' : ''} onClick={() => setTab('br')}>
            Rachunek zysków i strat
          </button>
        </nav>
      </header>
      {tab === 'forum' ? <ForumTab /> : <BiznesRadarTab />}
      <footer>
        Korzystaj rozważnie: pobieraj tylko treści, do których masz dostęp,
        i z poszanowaniem regulaminu oraz obciążenia serwisów (backend robi
        1,5 s przerwy między requestami).
      </footer>
    </div>
  )
}
