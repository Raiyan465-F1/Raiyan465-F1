#!/usr/bin/env python3
"""Fetches the numbers the panels draw and writes data/live.json.

    GITHUB_TOKEN=... python3 scripts/fetch.py

Standard library only. Needs a token because the contribution calendar is
only available through the GraphQL API; the default token of a GitHub
Actions run is enough. On any failure it exits non-zero and leaves the
existing data/live.json untouched.
"""
import datetime
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}
QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date weekday contributionCount contributionLevel } }
      }
    }
  }
}
"""


def call(url, token, payload=None):
    req = urllib.request.Request(url, data=json.dumps(payload).encode() if payload else None)
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "profile-panels")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def main():
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        sys.exit("fetch.py: set GITHUB_TOKEN")
    login = json.load(open(os.path.join(ROOT, "profile.json")))["login"]

    answer = call("https://api.github.com/graphql", token, {"query": QUERY, "variables": {"login": login}})
    if answer.get("errors") or not (answer.get("data") or {}).get("user"):
        sys.exit("fetch.py: GraphQL error: %s" % json.dumps(answer.get("errors") or answer)[:400])
    cal = answer["data"]["user"]["contributionsCollection"]["contributionCalendar"]

    weeks, months, last_month = [], [], None
    for i, week in enumerate(cal["weeks"]):
        days = [None] * 7                      # None = a day outside the calendar (first/last partial week)
        for day in week["contributionDays"]:
            days[day["weekday"]] = {
                "date": day["date"],
                "count": day["contributionCount"],
                "level": LEVELS.get(day["contributionLevel"], 0),
            }
        weeks.append(days)
        first = datetime.date.fromisoformat(week["contributionDays"][0]["date"])
        if first.month != last_month:
            if last_month is not None:
                months.append({"name": first.strftime("%b"), "week": i})
            last_month = first.month

    user = call("https://api.github.com/users/" + login, token)
    live = {
        "updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d"),
        "total": cal["totalContributions"],
        "counters": {"public_repos": user.get("public_repos"), "followers": user.get("followers")},
        "months": months,
        "weeks": weeks,
    }
    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
    with open(os.path.join(ROOT, "data", "live.json"), "w") as f:
        json.dump(live, f, separators=(",", ":"))
    print("fetch.py: %d contributions over %d weeks, %s repos, %s followers" % (
        live["total"], len(weeks), live["counters"]["public_repos"], live["counters"]["followers"]))


if __name__ == "__main__":
    main()
