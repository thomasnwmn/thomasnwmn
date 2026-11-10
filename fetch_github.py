"""Fetches GitHub stats into the "github" section of data.json.

Needs GH_TOKEN. Skips the fetch when the stored data is fresh enough, so this can
run on the same frequent schedule as the manga fetch; pass --force to override.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

from profile_data import load_data, load_profile, now_iso, save_section
from render import parse_iso

MAX_AGE_HOURS = 12

LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}

QUERY = """
query {
  viewer {
    createdAt
    followers { totalCount }
    repositoriesContributedTo(first: 1, contributionTypes: [COMMIT, ISSUE, PULL_REQUEST, REPOSITORY]) {
      totalCount
    }
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount contributionLevel } }
      }
    }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false) {
      nodes {
        name
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
        defaultBranchRef {
          target {
            ... on Commit {
              history(author: {id: "%s"}) { totalCount }
            }
          }
        }
      }
    }
  }
}
"""


def make_request(url, headers, data=None, retries=3):
    if data:
        data = json.dumps(data).encode("utf-8")

    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                if response.status == 202:
                    # 202 Accepted means GitHub is computing stats in the background
                    time.sleep(2)
                    continue
                body = response.read().decode("utf-8")
                return json.loads(body) if body else None
        except urllib.error.URLError as e:
            print(f"Request failed for {url}: {e}")
            return None
    return None


def graphql(headers, query):
    result = make_request("https://api.github.com/graphql", headers, {"query": query})
    if not result or "errors" in result:
        print(f"GraphQL request failed: {result.get('errors') if result else 'network/auth error'}")
        return None
    return result["data"]["viewer"]


def lines_of_code(headers, username, repos, old_cache, exclude):
    """Per-repo [added, deleted] for commits authored by the user."""
    cache = {}
    for repo in repos:
        name = repo["name"]
        if name in exclude:
            continue
        contributors = make_request(
            f"https://api.github.com/repos/{username}/{name}/stats/contributors", headers)
        if isinstance(contributors, list):
            added = deleted = 0
            for contributor in contributors:
                if (contributor.get("author") or {}).get("login", "").lower() == username.lower():
                    for week in contributor.get("weeks", []):
                        added += week.get("a", 0)
                        deleted += week.get("d", 0)
            cache[name] = [added, deleted]
        elif name in old_cache:
            # GitHub was still computing this repo's stats (or the request failed):
            # keep the last known numbers instead of counting it as zero
            print(f"No stats for {name} this run, using cached values")
            cache[name] = old_cache[name]
    return cache


def fetch(token, old, profile):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "Stats-Updater",
    }

    me = graphql(headers, "query { viewer { id login } }")
    if not me:
        print("Failed to identify the token's user. Check that GH_TOKEN is valid and has 'read:user' scope.")
        return None
    viewer = graphql(headers, QUERY % me["id"])
    if not viewer:
        return None

    repos = viewer["repositories"]["nodes"]
    commits = 0
    languages = {}
    for repo in repos:
        target = (repo.get("defaultBranchRef") or {}).get("target") or {}
        commits += (target.get("history") or {}).get("totalCount", 0)
        for edge in (repo.get("languages") or {}).get("edges", []):
            entry = languages.setdefault(edge["node"]["name"], {"color": edge["node"].get("color"), "size": 0})
            entry["size"] += edge["size"]

    loc_cache = lines_of_code(headers, me["login"], repos, old.get("loc_cache", {}),
                              set(profile.get("loc_exclude_repos", [])))

    calendar = viewer["contributionsCollection"]["contributionCalendar"]
    weeks = [[{"date": day["date"], "count": day["contributionCount"],
               "level": LEVELS.get(day["contributionLevel"], 0)}
              for day in week["contributionDays"]]
             for week in calendar["weeks"]]

    return {
        "fetched_at": now_iso(),
        "created_at": viewer["createdAt"],
        "repos": len(repos),
        "contributed": viewer["repositoriesContributedTo"]["totalCount"],
        "stars": sum(repo.get("stargazerCount", 0) for repo in repos),
        "commits": commits,
        "followers": viewer["followers"]["totalCount"],
        "loc_add": sum(added for added, _ in loc_cache.values()),
        "loc_del": sum(deleted for _, deleted in loc_cache.values()),
        "languages": sorted(({"name": name, **entry} for name, entry in languages.items()),
                            key=lambda l: l["size"], reverse=True),
        "calendar": {"total": calendar["totalContributions"], "weeks": weeks},
        "loc_cache": dict(sorted(loc_cache.items())),
    }


if __name__ == "__main__":
    old = load_data().get("github", {})
    force = "--force" in sys.argv

    # Sample data never counts as fresh
    if not force and old.get("fetched_at") and not old.get("sample"):
        age_hours = (time.time() - parse_iso(old["fetched_at"]).timestamp()) / 3600
        if age_hours < MAX_AGE_HOURS:
            print(f"GitHub data is {age_hours:.1f}h old, skipping (use --force to refetch).")
            sys.exit(0)

    token = os.environ.get("GH_TOKEN")
    if not token:
        print("ERROR: GH_TOKEN environment variable is not set!")
        sys.exit(1)

    section = fetch(token, old, load_profile())
    if not section:
        sys.exit(1)
    changed = save_section("github", section)
    print("GitHub data updated." if changed else "GitHub data unchanged.")
