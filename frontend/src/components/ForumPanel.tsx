"use client";

/** Forum tab: linked PortalAnaliz topics, incremental sync, post timeline. */
import { useCallback, useEffect, useState } from "react";
import { IconArrowBigUp, IconLink, IconRefresh } from "@tabler/icons-react";
import {
  getForumPosts,
  getForumTopics,
  linkForumTopic,
  syncForumTopic,
} from "@/lib/api";
import { LoadingMessages } from "@/components/Loading";
import { fmtDate, relativeDate } from "@/lib/format";
import type { ForumPage, ForumTopic } from "@/lib/types";

export default function ForumPanel({ ticker }: { ticker: string }) {
  const [topics, setTopics] = useState<ForumTopic[]>([]);
  const [page, setPage] = useState(1);
  const [author, setAuthor] = useState("");
  const [authorInput, setAuthorInput] = useState("");
  const [sort, setSort] = useState<"new" | "top">("new");
  const [posts, setPosts] = useState<ForumPage | null>(null);
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState<string | null>(null); // "link" | "sync-{id}"
  const [error, setError] = useState<string | null>(null);

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
        <div className="card" key={post.phpbb_post_id} style={{ marginBottom: 8 }}>
          <div className="spread" style={{ marginBottom: 6 }}>
            <span className="row" style={{ gap: 8 }}>
              <span style={{ fontWeight: 500, fontSize: 13 }}>{post.author}</span>
              {post.upvotes != null && post.upvotes > 0 && (
                <span className="badge success" title="Głosy na forum">
                  <IconArrowBigUp size={11} style={{ verticalAlign: -1 }} /> {post.upvotes}
                </span>
              )}
            </span>
            <span className="small muted">{fmtDate(post.posted_at)}</span>
          </div>
          <p
            className="secondary"
            style={{ fontSize: 13, whiteSpace: "pre-wrap", margin: 0 }}
          >
            {post.content_text}
          </p>
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
  );
}
