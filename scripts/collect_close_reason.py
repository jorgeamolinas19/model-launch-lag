"""Fill issues.closed_by_fix (metrics §3): was the issue closed by a linked commit/PR?

GitHub's state_reason ('completed' vs 'not_planned') is a weak proxy: maintainers click
"close as completed" on duplicates and on "fixed in main, please reopen" alike. The
ClosedEvent's `closer` is the stronger signal: a Commit or PullRequest closer means code
landed; a null closer means someone closed it by hand (stale bot, duplicate, question).

    closed_by_fix = 1   closer is a PullRequest or Commit
                  = 0   closed, no closer object
                  NULL  still open

One GraphQL query per 40 issues via aliases; raw responses under raw/github/closers_<snap>/.
Resumable: rows with closed_by_fix already set are skipped.
"""
import datetime as dt, sqlite3
from pathlib import Path
from gh import graphql, save_raw

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "db" / "launch_lag.sqlite"
SNAP = dt.date.today().isoformat()
BATCH = 40

Q_ITEM = '''i%d: repository(owner:"%s", name:"%s") { issue(number:%d) {
  timelineItems(itemTypes:[CLOSED_EVENT], last:1) { nodes { ... on ClosedEvent {
    closer { __typename ... on PullRequest { number merged } ... on Commit { oid } } } } } } }'''


def main():
    con = sqlite3.connect(DB, timeout=60)
    repos = dict(con.execute("SELECT id, repo FROM frameworks"))
    todo = con.execute("""SELECT DISTINCT framework_id, number FROM issues
                          WHERE excluded=0 AND closed_at IS NOT NULL AND closed_by_fix IS NULL
                          ORDER BY framework_id, number""").fetchall()
    print(f"{len(todo)} closed issues without closer info")
    raw = ROOT / "raw" / "github" / f"closers_{SNAP}"
    for b in range(0, len(todo), BATCH):
        chunk = todo[b:b + BATCH]
        parts = []
        for k, (fw, num) in enumerate(chunk):
            owner, name = repos[fw].split("/")
            parts.append(Q_ITEM % (k, owner, name, num))
        data = graphql("query { " + " ".join(parts) + " }")
        save_raw(data, raw, f"batch_{b // BATCH:04d}")
        for k, (fw, num) in enumerate(chunk):
            node = (data.get(f"i{k}") or {}).get("issue") or {}
            nodes = ((node.get("timelineItems") or {}).get("nodes") or [])
            closer = (nodes[-1].get("closer") if nodes else None) or None
            fix = 1 if closer and closer.get("__typename") in ("PullRequest", "Commit") else 0
            con.execute("UPDATE issues SET closed_by_fix=? WHERE framework_id=? AND number=?", (fix, fw, num))
        con.commit()
        print(f"  {min(b + BATCH, len(todo))}/{len(todo)}", flush=True)
    rows = con.execute("""SELECT framework_id, count(distinct id), sum(closed_by_fix) FROM issues
                          WHERE excluded=0 AND closed_at IS NOT NULL GROUP BY 1""").fetchall()
    print("\npct_closed_by_fix (metrics §3) - closed kept issues with a PR/commit closer:")
    for fw, n, f in rows:
        print(f"  {fw:<13}{f:>5}/{n:<5}{100 * f / n:>5.0f}%")
    print("  state_reason='completed' as a proxy would have said:")
    for fw, n, c in con.execute("""SELECT framework_id, count(distinct id), sum(state_reason='completed')
                                   FROM issues WHERE excluded=0 AND closed_at IS NOT NULL GROUP BY 1"""):
        print(f"  {fw:<13}{c:>5}/{n:<5}{100 * c / n:>5.0f}%")


if __name__ == "__main__":
    main()
