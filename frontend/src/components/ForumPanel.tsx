"use client";

/** Forum tab: linked PortalAnaliz topics, incremental sync, post timeline. */
import { useCallback, useEffect, useState } from "react";
import {
  IconArrowBigUp,
  IconChevronDown,
  IconChevronUp,
  IconLink,
  IconRefresh,
  IconSparkles,
} from "@tabler/icons-react";
import {
  getForumPosts,
  getForumTopics,
  linkForumTopic,
  syncForumTopic,
} from "@/lib/api";
import { LoadingMessages } from "@/components/Loading";
import { fmtDate, relativeDate } from "@/lib/format";
import type {
  ForumDistilledFact,
  ForumExpectationClaim,
  ForumExpectations,
  ForumIntelligence,
  ForumPage,
  ForumTopic,
} from "@/lib/types";

function factTone(fact: ForumDistilledFact) {
  if (fact.polarity === "positive") return "success";
  if (fact.polarity === "negative") return "danger";
  return "neutral";
}

// Curated investment-argument categories the AI distiller may tag a claim
// with, in display order. Anything else (including the current backend's
// post-level "fact-claim" tag — see lib/types.ts ForumExpectationClaim doc)
// lands in the "Pozostałe argumenty" catch-all below, so a taxonomy change
// on the backend degrades gracefully instead of hiding claims.
const CLAIM_TYPE_GROUPS: { key: string; label: string }[] = [
  { key: "expectation", label: "Oczekiwania" },
  { key: "catalyst", label: "Katalizatory" },
  { key: "risk", label: "Ryzyka" },
  { key: "valuation", label: "Wycena" },
];
const OTHER_GROUP = { key: "__other", label: "Pozostałe argumenty" };

const CONFIDENCE_LABELS: Record<string, string> = {
  low: "niska pewność",
  medium: "średnia pewność",
  high: "wysoka pewność",
};

function confidenceLabel(confidence: string): string {
  return CONFIDENCE_LABELS[confidence] ?? confidence;
}

function confidenceTone(confidence: string): string {
  if (confidence === "high") return "accent";
  if (confidence === "medium") return "neutral";
  return "muted";
}

/**
 * Lead card of the Forum tab: AI-distilled investment-expectation claims,
 * grouped by argument type, no author names (the user only cares about the
 * argument, not who posted it — see task brief). Falls back to an explicit
 * empty state rather than disappearing, so it's obvious a refresh would help.
 */
function ExpectationsCard({
  expectations,
}: {
  expectations: ForumExpectations | null | undefined;
}) {
  const claims = expectations?.claims ?? [];

  const grouped = new Map<string, ForumExpectationClaim[]>();
  for (const claim of claims) {
    const key = CLAIM_TYPE_GROUPS.some((g) => g.key === claim.type) ? claim.type : OTHER_GROUP.key;
    const bucket = grouped.get(key) ?? [];
    bucket.push(claim);
    grouped.set(key, bucket);
  }
  const groups = [...CLAIM_TYPE_GROUPS, OTHER_GROUP].filter(
    (g) => (grouped.get(g.key)?.length ?? 0) > 0,
  );

  return (
    <div className="card expectations" style={{ marginBottom: 16 }}>
      <p className="expectations-title">
        <IconSparkles size={14} /> Oczekiwania inwestycyjne (forum)
      </p>
      {claims.length === 0 ? (
        <p className="empty-state">
          Brak wydestylowanych oczekiwań — odśwież spółkę (wymaga klucza API).
        </p>
      ) : (
        <div className="expectations-groups">
          {groups.map((group) => (
            <div className="expectations-group" key={group.key}>
              <p className="group-label">{group.label}</p>
              <div className="claim-list">
                {(grouped.get(group.key) ?? []).map((claim, index) => (
                  <div className="claim" key={`${group.key}-${index}`}>
                    <p className="claim-text">{claim.claim}</p>
                    <span className={`badge ${confidenceTone(claim.confidence)}`}>
                      {confidenceLabel(claim.confidence)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
      {expectations && claims.length > 0 && (
        <p className="expectations-meta small muted">
          destylat AI z {expectations.source_post_count} postów
          {expectations.model ? ` · ${expectations.model}` : ""}
          {expectations.updated_at ? ` · ${fmtDate(expectations.updated_at)}` : ""}
        </p>
      )}
    </div>
  );
}

/**
 * Secondary, de-emphasised forum context: industry tag, 30d activity as a
 * tiny muted line (no longer a stat-card — the expectations above are the
 * headline now), and the older heuristic `distilled_facts` list ONLY as a
 * fallback for companies without AI expectations yet.
 */
function ForumContext({ intelligence }: { intelligence: ForumIntelligence | null | undefined }) {
  if (!intelligence) return null;
  const hasExpectations = (intelligence.expectations?.claims.length ?? 0) > 0;
  const facts = intelligence.distilled_facts.slice(0, 8);

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div className="spread" style={{ marginBottom: 6 }}>
        <p style={{ fontWeight: 500, fontSize: 13, margin: 0 }}>Kontekst forum</p>
        {intelligence.industry_type && (
          <span className="badge neutral">{intelligence.industry_type}</span>
        )}
      </div>
      <p className="small muted" style={{ margin: 0 }}>
        posty 30d: {intelligence.last_30d_post_count} · aktywni 30d:{" "}
        {intelligence.last_30d_active_user_count}
        {intelligence.community_sentiment ? ` · sentyment: ${intelligence.community_sentiment}` : ""}
      </p>

      {!hasExpectations && (
        <div style={{ marginTop: 12 }}>
          {facts.length > 0 ? (
            <div style={{ display: "grid", gap: 8 }}>
              {facts.map((fact, index) => (
                <div key={`${fact.fact}-${index}`} className="source-row" style={{ alignItems: "start" }}>
                  <span className={`badge ${factTone(fact)}`}>{fact.confidence}</span>
                  <span>
                    <strong className="secondary">{fact.topic}</strong>
                    <span className="small muted" style={{ marginLeft: 6 }}>
                      {fact.type}
                    </span>
                    <br />
                    {fact.fact}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="small muted">Brak wydestylowanych faktów po ostatniej synchronizacji.</p>
          )}
        </div>
      )}
    </div>
  );
}

export default function ForumPanel({
  ticker,
  intelligence,
}: {
  ticker: string;
  intelligence?: ForumIntelligence | null;
}) {
  const [topics, setTopics] = useState<ForumTopic[]>([]);
  const [page, setPage] = useState(1);
  const [author, setAuthor] = useState("");
  const [authorInput, setAuthorInput] = useState("");
  const [sort, setSort] = useState<"new" | "top">("new");
  const [posts, setPosts] = useState<ForumPage | null>(null);
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState<string | null>(null); // "link" | "sync-{id}"
  const [error, setError] = useState<string | null>(null);
  // Raw posts are demoted behind a toggle — the expectations card above is
  // the primary read; this stays for verification/drill-down (task brief).
  const [showRawPosts, setShowRawPosts] = useState(false);

  const loadTopics = useCallback(
    () => getForumTopics(ticker).then(setTopics).catch(() => setTopics([])),
    [ticker],
  );
  const loadPosts = useCallback(
    () =>
      getForumPosts(ticker, page, author || undefined, sort)
        .then(setPosts)
        .catch((err) => setError(err instanceof Error ? err.message : String(err))),
    [ticker, page, author, sort],
  );

  useEffect(() => {
    void loadTopics();
  }, [loadTopics]);
  useEffect(() => {
    void loadPosts();
  }, [loadPosts]);

  const handleLink = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!url.trim()) return;
    setBusy("link");
    setError(null);
    try {
      await linkForumTopic(url.trim(), ticker);
      setUrl("");
      await loadTopics();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  const handleSync = async (topicId: number) => {
    setBusy(`sync-${topicId}`);
    setError(null);
    try {
      const result = await syncForumTopic(topicId);
      await Promise.all([loadTopics(), loadPosts()]);
      if (result.new_posts === 0) setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  const totalPages = posts ? Math.max(1, Math.ceil(posts.total / posts.page_size)) : 1;

  return (
    <div>
      {error && <div className="error-box">{error}</div>}

      <ExpectationsCard expectations={intelligence?.expectations} />
      <ForumContext intelligence={intelligence} />

      <div className="card" style={{ marginBottom: 16 }}>
        <p style={{ fontWeight: 500, fontSize: 13, marginBottom: 8 }}>
          Powiązane wątki PortalAnaliz
        </p>
        {topics.length === 0 && (
          <p className="small muted">Brak wątków — wklej link do wątku spółki poniżej.</p>
        )}
        {topics.map((topic) => (
          <div className="spread" key={topic.id} style={{ padding: "6px 0", fontSize: 13 }}>
            <span>
              <a href={topic.url} target="_blank" rel="noreferrer" className="secondary">
                {topic.title ?? topic.url}
              </a>
              <span className="small muted" style={{ marginLeft: 8 }}>
                synchronizacja: {relativeDate(topic.last_synced_at)}
              </span>
            </span>
            <button
              className="btn"
              style={{ fontSize: 12 }}
              disabled={busy === `sync-${topic.id}`}
              onClick={() => handleSync(topic.id)}
            >
              <IconRefresh
                size={13}
                className={busy === `sync-${topic.id}` ? "spin" : ""}
              />
              Synchronizuj
            </button>
          </div>
        ))}
        <form className="row" style={{ marginTop: 10 }} onSubmit={handleLink}>
          <input
            placeholder="https://portalanaliz.pl/forum/viewtopic.php?f=…&t=…"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            style={{ flex: 1 }}
          />
          <button className="btn" type="submit" disabled={busy === "link"}>
            <IconLink size={13} /> Powiąż wątek
          </button>
        </form>
      </div>

      <button
        className="btn"
        onClick={() => setShowRawPosts((v) => !v)}
        aria-expanded={showRawPosts}
      >
        {showRawPosts ? <IconChevronUp size={13} /> : <IconChevronDown size={13} />}
        {showRawPosts ? "Ukryj surowe posty" : `Pokaż surowe posty (${posts?.total ?? 0})`}
      </button>

      {showRawPosts && (
        <div style={{ marginTop: 12 }}>
          <div className="spread" style={{ marginBottom: 10 }}>
            <form
              className="row"
              onSubmit={(e) => {
                e.preventDefault();
                setPage(1);
                setAuthor(authorInput.trim());
              }}
            >
              <input
                placeholder="filtruj po autorze, np. OBS"
                value={authorInput}
                onChange={(e) => setAuthorInput(e.target.value)}
                style={{ width: 200 }}
              />
              <button className="btn" type="submit">
                Filtruj
              </button>
            </form>
            <span className="row">
              <span className="small muted">{posts ? `${posts.total} postów` : ""}</span>
              <div className="tabs" style={{ margin: 0, borderBottom: "none" }}>
                <button
                  className={sort === "new" ? "active" : ""}
                  onClick={() => { setSort("new"); setPage(1); }}
                >
                  Najnowsze
                </button>
                <button
                  className={sort === "top" ? "active" : ""}
                  onClick={() => { setSort("top"); setPage(1); }}
                  title="Wg głosów — kolejność, którą dostanie analiza AI"
                >
                  Najlepsze
                </button>
              </div>
            </span>
          </div>

          {!posts && !error && (
            <LoadingMessages
              messages={["Wczytuję posty z forum…", "Układam dyskusję chronologicznie…"]}
            />
          )}
          {posts && posts.posts.length === 0 && (
            <p className="empty-state">Brak postów — powiąż wątek i kliknij Synchronizuj.</p>
          )}

          {posts?.posts.map((post) => (
            <div className="card raw-post" key={post.phpbb_post_id} style={{ marginBottom: 8 }}>
              <div className="spread">
                <span className="row" style={{ gap: 8 }}>
                  <span className="small muted">{post.author}</span>
                  {post.upvotes != null && post.upvotes > 0 && (
                    <span className="badge success" title="Głosy na forum">
                      <IconArrowBigUp size={11} style={{ verticalAlign: -1 }} /> {post.upvotes}
                    </span>
                  )}
                </span>
                <span className="small muted">{fmtDate(post.posted_at)}</span>
              </div>
            </div>
          ))}

          {posts && posts.total > posts.page_size && (
            <div className="row" style={{ justifyContent: "center", marginTop: 12 }}>
              <button
                className="btn"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
              >
                Nowsze
              </button>
              <span className="small muted">
                {page} / {totalPages}
              </span>
              <button
                className="btn"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
              >
                Starsze
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
