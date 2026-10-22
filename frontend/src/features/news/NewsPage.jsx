import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, CircleHelp, Clock3, RefreshCw } from "lucide-react";
import { api, isSafeArticleUrl } from "../../lib/api";
import { errorText } from "../../lib/formatters";
import { ErrorState } from "../../components/feedback/ErrorState";
import { PageTitle } from "../../components/ui/PageTitle";
import { TableEmpty } from "../../components/feedback/TableEmpty";
export function NewsPage() {
  const query = useQuery({
    queryKey: ["news", "live"],
    queryFn: () => api("/api/v1/news/live"),
  });
  const status = useQuery({
    queryKey: ["news-status"],
    queryFn: () => api("/api/v1/news/status"),
  });
  const news = [...(query.data ?? [])].sort((a, b) => {
    const time = (value) => {
      const parsed = typeof value === "string" ? Date.parse(value) : NaN;
      return Number.isFinite(parsed) ? parsed : Number.NEGATIVE_INFINITY;
    };
    return time(b.published_at) - time(a.published_at);
  });
  const displayTimestamp = (value) => {
    if (typeof value !== "string") return "Publication time unavailable";
    const parsed = Date.parse(value);
    return Number.isFinite(parsed) ? new Date(parsed).toLocaleString() : value;
  };
  return (
    <>
      <PageTitle
        eyebrow="NEWS INTELLIGENCE"
        title="News terminal"
        subtitle="Provider-attributed articles only. Sample headlines are not shown or mixed into live results."
        action={
          <button
            className="btn btn-secondary"
            onClick={() => void query.refetch()}
          >
            <RefreshCw size={15} /> Refresh provider
          </button>
        }
      />
      {status.data && !status.data.configured && (
        <div className="simulation-banner warning">
          <CircleHelp size={17} />
          <div>
            <b>News provider is not configured</b>
            <span>
              {status.data.message} No sample articles or invented publication
              times are displayed.
            </span>
          </div>
          <span className="banner-badge">NO LIVE FEED</span>
        </div>
      )}
      {query.isError && <ErrorState message={errorText(query.error)} />}
      <div className="news-grid">
        {news.map((article, i) => (
          <article className="panel news-card" key={String(article.id ?? i)}>
            <div className="eyebrow">
              {String(article.category ?? "News")} ·{" "}
              {String(article.source ?? "Provider source unavailable")}
            </div>
            <h2>{String(article.title ?? "Untitled headline")}</h2>
            <p>
              {String(
                article.description ??
                  "No description supplied by the provider.",
              )}
            </p>
            <div className="news-footer">
              <span>
                <Clock3 size={13} />
                {displayTimestamp(article.published_at)}
              </span>
              {Boolean(article.retrieved_at) && (
                <span>Retrieved {displayTimestamp(article.retrieved_at)}</span>
              )}
              {typeof article.url === "string" &&
                isSafeArticleUrl(article.url) && (
                  <a
                    href={article.url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Open original <ArrowUpRight size={13} />
                  </a>
                )}
            </div>
          </article>
        ))}
      </div>
      {!query.isLoading &&
        !query.isError &&
        !news.length &&
        status.data?.configured && (
          <div className="panel">
            <TableEmpty>The provider returned no matching articles.</TableEmpty>
          </div>
        )}
    </>
  );
}
