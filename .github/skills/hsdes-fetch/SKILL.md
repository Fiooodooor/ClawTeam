---
name: hsdes-fetch
description: >
  Fetch and summarize Intel HSDES (HSD-ES) tickets using Kerberos
  authentication and the HSDES REST API. Use this skill when the user
  asks to access, read, query, or summarize an HSDES article or sighting.
---

# HSDES Ticket Fetcher

## When to use this skill

Use this skill when the user:

- Asks to access, fetch, or read an HSDES ticket/article/sighting
- Provides an HSDES URL or article ID
- Asks about bug details from the Intel HSDES system
- Needs a summary of an HSD ticket for a status update or meeting

## Prerequisites — Kerberos Authentication

Before accessing HSDES, a valid Kerberos ticket is required.

### Check for existing ticket

```bash
klist 2>/dev/null | grep -q "krbtgt" && echo "TICKET OK" || echo "NO TICKET"
```

### If no ticket exists

1. Ensure `/etc/krb5.conf` is configured with the Intel realm.
   See [references/hsdes_access_from_copilot.md](references/hsdes_access_from_copilot.md)
   for full setup instructions.

2. Authenticate:

```bash
kinit <idsid>@GER.CORP.INTEL.COM
```

The IDSID is typically the system username. Regional realms:

| Region            | Realm                |
|-------------------|----------------------|
| Israel / Europe   | `GER.CORP.INTEL.COM` |
| Americas          | `AMR.CORP.INTEL.COM` |
| Global (fallback) | `CORP.INTEL.COM`     |

## How to fetch an HSDES article

### Extract article ID

If the user provides a URL like
`https://hsdes.intel.com/appstore/article-one/#/article/22021456008`,
extract the numeric ID: `22021456008`.

### Fetch via REST API

```bash
curl --negotiate -u : -s -L \
  "https://hsdes-api.intel.com/rest/article/<article-id>"
```

The response is a JSON object with a `data` array containing the article
fields.

## How to parse and present results

### Summary table

Extract and display these fields:

| Field             | JSON key           |
|-------------------|--------------------|
| Title             | `title`            |
| Status            | `status`           |
| Priority          | `priority`         |
| Owner             | `owner`            |
| Component         | `component`        |
| Release           | `release`          |
| Submitted by      | `submitted_by`     |
| Submitted date    | `submitted_date`   |
| Last updated      | `updated_date`     |
| Release affected  | `release_affected` |
| Collaborators     | `collaborators`    |

### Description

The `description` field contains HTML. Clean it:

- Replace `<img>` tags with `[IMAGE]`
- Extract `href` from `<a>` tags
- Strip remaining HTML tags
- Unescape HTML entities

### Comments

The `comments` field uses `++++<numeric-id> <author-idsid>` as delimiters.
Split on this pattern and present each comment with:

- Author IDSID
- Comment content (HTML-cleaned)
- Chronological order

### Action items

Identify from the comment history:

- Open action items and responsible parties
- Deadlines or work-week targets mentioned
- Blocking issues or dependencies

## How to search HSDES

To run a saved query:

```bash
curl --negotiate -u : -s -L \
  "https://hsdes-api.intel.com/rest/query/<query-id>/run"
```

## Common fields reference

| Field                                          | Description                   |
|------------------------------------------------|-------------------------------|
| `sighting.env_found`                           | Environment (silicon, FPGA)   |
| `server_soc_networking.sighting.exposure`      | Exposure level                |
| `server_soc_networking.sighting.steps_to_reproduce` | Reproduction steps       |
| `server_soc_networking.sighting.workaround_applied` | Workaround status        |
| `server_soc_networking.sighting.platform`      | Platform type                 |

## Troubleshooting

| Error | Fix |
|-------|-----|
| curl returns HTML instead of JSON | Kerberos ticket expired — run `kinit` |
| `Cannot find KDC for realm` | Check `/etc/krb5.conf` — see references/ |
| `Client not found in Kerberos database` | Wrong IDSID or wrong realm |
| `--negotiate` not working | Ensure `krb5-user` package is installed |
