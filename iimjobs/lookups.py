"""/iimjobs/skills, /iimjobs/categories, /iimjobs/locations,
/iimjobs/industries, /iimjobs/autocomplete — the vocabularies behind the
search filters (the skill table and the industry list live from the site,
cached; categories and locations from refdata) and the search box's
suggestions; plus the skill-name -> tag-id resolution the job search uses."""
from iimjobs import cache_config as ttl
from iimjobs import fetch, refdata
from iimjobs import parsers as P
from iimjobs import shared as S


# ---- skills ------------------------------------------------------------------------------------------------

def skill_table():
    """The parsed /tags table (cached a day: ~2,700 skills in 9 categories)."""
    return fetch.shared_raw("skill_table", {}, lambda: P.skill_table(fetch.tags()), ttl.TAGS_RAW_CACHE)


def _skill_index():
    index = {}
    for block in skill_table():
        for skill in block["skills"]:
            key = " ".join((skill["name"] or "").lower().split())
            if key and key not in index:
                index[key] = skill
            if skill["id"] is not None:
                index.setdefault(str(skill["id"]), skill)
    return index


def skill_index():
    return fetch.memoized(("iimjobs", "skill_index"), _skill_index, ttl=fetch.MEMO_TTL)


def resolve_skill_ids(skills):
    """The validated `skill` list (names lower-cased, ids as ints) -> (tag ids,
    [{id, name, link}]). A name missing from the table is tried as a /k/
    slug (tag_info); still unknown -> ValueError (a 400)."""
    if not skills:
        return None, []
    index = skill_index()
    ids, refs_out = [], []
    for item in skills:
        if isinstance(item, int):
            hit = index.get(str(item)) or {"id": item, "name": None, "link": None}
        else:
            hit = index.get(item)
            if hit is None:
                info = fetch.tag_info(S.slugify(item) or item)
                hit = P.tag_info(info) if info else None
            if hit is None or hit.get("id") is None:
                raise ValueError(f"'{item}' is not a skill iimjobs knows; see /iimjobs/skills or /iimjobs/autocomplete.")
        if hit["id"] not in ids:
            ids.append(hit["id"])
            refs_out.append({"id": hit["id"], "name": hit.get("name"), "link": hit.get("link")})
    return ids, refs_out


def skills(category=None, query=None, limit=None):
    """Every skill tag with its live job count, by job category. `category`
    narrows to one or more categories, `query` to names containing it,
    `limit` keeps the top-N by job count per category."""
    needle = (query or "").lower()
    out = []
    for block in skill_table():
        cat = block["category"] or {}
        if category and cat.get("id") not in category:
            continue
        rows = block["skills"]
        if needle:
            rows = [s for s in rows if needle in (s["name"] or "").lower()]
        rows = sorted(rows, key=lambda s: -(s["jobs_count"] or 0))
        if limit:
            rows = rows[:limit]
        out.append({"category": cat or None, "skills": rows, "count": len(rows)})
    return {"categories": out, "count": sum(b["count"] for b in out)}


# ---- categories / locations / industries ---------------------------------------------------------------

def categories():
    """The 9 job categories (the `category` filter's ids / slugs / names, the /c/ pages)."""
    rows = [P.category_ref(cid) for cid in refdata.CATEGORIES]
    return {"categories": rows, "count": len(rows)}


def locations():
    """The location picker: the `location` filter's ids and names, with the
    umbrella entries (Metros, Anywhere in India, Overseas, Delhi NCR) and
    their members."""
    groups = refdata.LOCATION_GROUPS
    member_of = {}
    for gid, members in groups.items():
        for m in members:
            member_of.setdefault(m, []).append(gid)
    rows = [{"id": loc_id, "name": name, "is_remote": name.lower() in refdata.REMOTE_NAMES,
             "is_group": loc_id in groups, "groups": [refdata.LOCATIONS.get(gid) for gid in member_of.get(loc_id, [])]}
            for loc_id, name in refdata.LOCATIONS.items()]
    group_rows = [{"id": gid, "name": refdata.LOCATIONS.get(gid),
                   "members": [{"id": m, "name": refdata.LOCATIONS.get(m)} for m in members if m in refdata.LOCATIONS]}
                  for gid, members in groups.items()]
    return {"locations": rows, "count": len(rows), "groups": group_rows}


def industries():
    """The industry filter's vocabulary, live from the site: the industries
    jobs are filed under and the trending startup sectors (FinTech, B2B
    SaaS, …); pass a `name` or `filter_value` as /iimjobs/jobs/search's
    `industry`."""
    table = P.industry_table(fetch.industries())
    return {**table, "count": len(table["industries"]) + len(table["trending_industries"])}


# ---- autocomplete --------------------------------------------------------------------------------------------

def autocomplete(query, limit=10):
    """The search box's suggestions for `query` (skill and role names), each
    with the matching skill tag when the table has one."""
    names = fetch.suggest(query)[:limit]
    index = skill_index()
    out = []
    for name in names:
        hit = index.get(" ".join(name.lower().split()))
        out.append({"name": name, "skill": {"id": hit["id"], "jobs_count": hit["jobs_count"], "link": hit["link"]}
                    if hit else None})
    return {"query": query, "suggestions": out, "count": len(out)}


# ---- filter echoes ---------------------------------------------------------------------------------------------

def category_refs(ids):
    return [P.category_ref(c) for c in (ids or [])] or None


def location_refs(ids):
    return [{"id": i, "name": refdata.LOCATIONS.get(i)} for i in (ids or [])] or None


def industry_refs(values):
    """['t-1', '2'] -> [{id: 1, name: 'FinTech', is_trending: True}, {id: 2, …}]."""
    out = []
    for value in values or []:
        value = str(value)
        if value.startswith("t-"):
            iid = S.to_int(value[2:])
            out.append({"id": iid, "name": refdata.TRENDING_INDUSTRIES.get(iid), "is_trending": True})
        else:
            iid = S.to_int(value)
            out.append({"id": iid, "name": refdata.INDUSTRIES.get(iid), "is_trending": False})
    return out or None
