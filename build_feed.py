#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_feed.py — Build an Atom feed of GitHub Releases for every repo starred by a user.

STRICTLY READ-ONLY. Only calls public GitHub REST endpoints:
  GET /users/{user}/starred            -> current starred repo list
  GET /repos/{owner}/{repo}/releases   -> published Releases of each repo

Why this satisfies the rules:
  * Plain git tags never appear: only real GitHub Releases are listed here.
  * Drafts never appear: the releases endpoint hides drafts from non-collaborators,
    and we additionally filter out anything with draft=true as a safeguard.
  * Pre-releases DO appear (alpha/beta/rc etc.), because they are published releases.
  * No state is kept between runs: the feed is rebuilt deterministically from the
    current API snapshot every run, so an entry never duplicates, newly starred
    repos appear on the next run, and unstarred repos disappear on the next run.
"""
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from xml.etree import ElementTree

USER = os.environ.get("GH_USER", "mikechen25")
TOKEN = os.environ.get("GH_TOKEN", "")  # auto-injected GITHUB_TOKEN (no PAT involved)
API = "https://api.github.com"
PAGE_STARS = 100
PAGE_RELEASES = 100          # one request per repo; newest 100 releases window
MAX_REPOS = int(os.environ.get("GH_MAX_REPOS", "0") or "0") or None  # optional test cap
MAX_ENTRIES = 500            # keep the newest N releases in the feed
OUT_DIR = os.environ.get("OUT_DIR", "_site")
FEED_URL = os.environ.get(
    "FEED_URL",
    "https://{user}.github.io/github-starred-releases/index.xml".format(user=USER),
)

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")  # chars illegal in XML 1.0


def esc(value):
    """XML-escape text and strip control characters."""
    if value is None:
        return ""
    return html.escape(_CTRL.sub("", str(value)))


def _headers():
    h = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "starred-releases-feed/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if TOKEN:
        h["Authorization"] = "Bearer {t}".format(t=TOKEN)
    return h


def get_json(url):
    req = urllib.request.Request(url, headers=_headers())
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def get_all_pages(url):
    """Follow pagination of a GitHub list endpoint until an empty page."""
    result = []
    page = 1
    while True:
        sep = "&" if "?" in url else "?"
        try:
            batch = get_json("{u}{s}per_page={n}&page={p}".format(u=url, s=sep, n=PAGE_STARS, p=page))
        except urllib.error.HTTPError as err:
            print("WARN: {u} page {p} -> HTTP {c}".format(u=url, p=page, c=err.code), file=sys.stderr)
            break
        if not batch:
            break
        result.extend(batch)
        if len(batch) < PAGE_STARS:
            break
        page += 1
    return result


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def entry_title(entry):
    tag = entry["tag"]
    name = entry["name"]
    if name and name.lower() != tag.lower():
        # Name often already starts with the tag ("v1.2.3 — Some title") -> avoid duplication.
        if name.lower().startswith(tag.lower()):
            return "{repo} {name}".format(repo=entry["repo"], name=name)
        return "{repo} {tag} - {name}".format(repo=entry["repo"], tag=tag, name=name)
    return "{repo} {tag}".format(repo=entry["repo"], tag=tag)


def entry_content_html(entry):
    kind = "Pre-release" if entry["pre"] else "Release"
    body = entry["body"].strip()
    body_html = "<pre>{body}</pre>".format(body=esc(body)) if body else "<p>(no release notes)</p>"
    return (
        "<p><b>{repo}</b> {tag}</p>"
        "<p>Version / tag: {tag}</p>"
        "<p>Published: {published} ({kind})</p>"
        "{body}"
    ).format(
        repo=esc(entry["repo"]),
        tag=esc(entry["tag"]),
        published=esc(entry["published"]),
        kind=esc(kind),
        body=body_html,
    )


def main():
    started = time.time()
    print("== GitHub Starred Releases feed builder ==")
    print("user: {u} | authenticated: {a}".format(u=USER, a=bool(TOKEN)))

    print("fetching starred repos ...")
    stars = get_all_pages("{a}/users/{u}/starred".format(a=API, u=USER))
    print("starred repos: {n}".format(n=len(stars)))

    if MAX_REPOS:
        print("TEST CAP: only processing {n} repos".format(n=MAX_REPOS))
        stars = stars[:MAX_REPOS]

    entries = []
    skipped = 0
    for repo in stars:
        full = repo["full_name"]
        url = "{a}/repos/{f}/releases?per_page={n}".format(a=API, f=full, n=PAGE_RELEASES)
        try:
            releases = get_json(url)
        except urllib.error.HTTPError as err:
            skipped += 1
            print("skip {f}: HTTP {c}".format(f=full, c=err.code), file=sys.stderr)
            continue
        for rel in releases:
            if rel.get("draft"):
                continue  # defensive; drafts are invisible to this token anyway
            entries.append({
                "repo": full,
                "id": rel["id"],
                "tag": rel.get("tag_name") or "",
                "name": rel.get("name") or "",
                "published": rel.get("published_at") or now_iso(),
                "url": rel.get("html_url") or "",
                "body": rel.get("body") or "",
                "pre": bool(rel.get("prerelease")),
            })

    print("releases collected: {n} (repos skipped: {s})".format(n=len(entries), s=skipped))
    entries.sort(key=lambda e: e["published"], reverse=True)
    entries = entries[:MAX_ENTRIES]
    print("entries kept (newest {m}): {n}".format(m=MAX_ENTRIES, n=len(entries)))

    updated = now_iso()
    out = []
    out.append('<?xml version="1.0" encoding="utf-8"?>')
    out.append('<feed xmlns="http://www.w3.org/2005/Atom">')
    out.append("<title>GitHub Starred Releases - {u}</title>".format(u=esc(USER)))
    out.append("<id>{u}</id>".format(u=esc(FEED_URL)))
    out.append('<link rel="alternate" href="https://github.com/{u}?tab=stars"/>'.format(u=esc(USER)))
    out.append('<link rel="self" href="{u}"/>'.format(u=esc(FEED_URL)))
    out.append("<updated>{t}</updated>".format(t=updated))
    out.append("<author><name>{u}</name></author>".format(u=esc(USER)))
    out.append(
        "<subtitle>New GitHub Releases from starred repos. "
        "Real Releases only (no bare git tags, no drafts); pre-releases included. "
        "Updated hourly.</subtitle>"
    )
    for e in entries:
        out.append("<entry>")
        out.append("<title>{t}</title>".format(t=esc(entry_title(e))))
        out.append("<id>tag:github.com,2026:release:{i}</id>".format(i=e["id"]))
        if e["url"]:
            out.append('<link rel="alternate" href="{u}"/>'.format(u=esc(e["url"])))
        out.append("<published>{t}</published>".format(t=esc(e["published"])))
        out.append("<updated>{t}</updated>".format(t=esc(e["published"])))
        out.append('<content type="html">{c}</content>'.format(c=entry_content_html(e)))
        out.append("</entry>")
    out.append("</feed>")

    xml_text = "\n".join(out)
    # Hard validation: must be well-formed XML or we fail loudly (never ship a broken feed).
    ElementTree.fromstring(xml_text)

    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, "index.xml")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(xml_text + "\n")
    print("wrote {p} ({b} bytes) in {s:.1f}s".format(
        p=path, b=os.path.getsize(path), s=time.time() - started))


if __name__ == "__main__":
    main()
