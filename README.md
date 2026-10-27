# ws-sunset

USGS is decommissioning **WaterServices** (`waterservices.usgs.gov`) on **22 February 2027**. Before that, USGS
is degrading it on purpose so that automated users notice
([schedule](https://waterdata.usgs.gov/blog/wdfn-waterservices-degradation/), updated 27 Oct 2026):

| Date | What happens to every WaterServices request |
|---|---|
| 16 Nov 2026 | 2-second added delay |
| 11 Jan 2027 | 10-second delay |
| 25 Jan 2027 | 30-second delay |
| 27 Jan 2027 | redirected to the USGS notice for about 24 hours (restored 28 Jan) |
| 1 Feb 2027 | 60-second delay |
| 15 Feb 2027 | redirected for about 48 hours (restored 17 Feb) |
| 22 Feb 2027 | decommissioned |

Code that polls many sites one request at a time will feel the delays first. See also the
[decommission notice](https://waterdata.usgs.gov/blog/api-waterservices-decom/). Any code that calls it, or that uses
R `readNWIS*()` or the Python `dataretrieval.nwis` module, needs to move to the modernized
[Water Data APIs](https://api.waterdata.usgs.gov/ogcapi/v1/).

`ws-sunset` scans a codebase and lists every place that will break. Each hit comes with the
replacement and a link to the matching section of the official
[migration guide](https://api.waterdata.usgs.gov/docs/ogcapi/migration/). It reads files and prints
findings. It never edits code and has no dependencies.

```
pip install git+https://github.com/bonyohana/ws-sunset
ws-sunset path/to/repo            # human-readable; exit 1 if anything was found
ws-sunset path/to/repo --json     # for scripts and CI
```

```
src/usgs.js:1: [legacy-endpoint] waterservices.usgs.gov/nwis/iv
    -> https://api.waterdata.usgs.gov/ogcapi/v1/collections/continuous  (latest values: …/latest-continuous)
    note: one feature per observation, not grouped per time series; at most 3 years per query
    guide: https://api.waterdata.usgs.gov/docs/ogcapi/migration/#migrating-from-%2Fiv-to-%2Fcontinuous
src/usgs.js:50: [qualifiers-field] .qualifiers
    -> approval_status (Approved/Provisional) and qualifier (other codes)
```

## What it looks for

| Kind | Example | Points to |
|---|---|---|
| `legacy-endpoint` | `waterservices.usgs.gov/nwis/iv` | `/continuous` or `/latest-continuous` |
| | `/nwis/dv` | `/daily` |
| | `/nwis/site` | `/monitoring-locations`, `/time-series-metadata` |
| | `/nwis/gwlevels`, `/measurements` | `/field-measurements` (channel: `/channel-measurements`) |
| | `/nwis/peak` | `/peaks` |
| | `/nwis/stat`, `/nwis/qwdata` | the statistics and samples-data APIs |
| `legacy-host` | any other `waterservices.usgs.gov` reference | the new API root |
| `r-dataRetrieval` | `readNWISuv(...)`, `whatNWISdata(...)` | the `read_waterdata()` family |
| `py-dataretrieval` | `from dataretrieval import nwis`, `nwis.get_iv(...)` | `dataretrieval.waterdata` |
| `provisional-check` | `'P' in v['qualifiers']` | `approval_status == 'Provisional'` |
| `qualifiers-field` | reading `qualifiers` in a file that uses WaterServices | `approval_status` plus `qualifier` |
| `rdb-cd-column` | `X_00060_cd` | `approval_status` plus `qualifier` |

**Why the provisional checks get their own kind:** the new APIs moved approval status out of
`qualifiers` and into its own `approval_status` field ("Approved" or "Provisional"). Every other
qualifier moved to `qualifier`. If a port carries over a check like "no `P` in qualifiers means
final", it will treat provisional data as approved. A null `qualifier` doesn't mean approved.

## In CI

As a GitHub Action, it reports findings and passes by default:

```yaml
- uses: actions/checkout@v4
- uses: bonyohana/ws-sunset@v0.1.2
  with:
    path: .
    fail-on-findings: "false"   # set "true" to fail the build once you've migrated
```

Or run the command directly:

```yaml
- run: pip install git+https://github.com/bonyohana/ws-sunset && ws-sunset .
```

## Limits

These are pattern matches. Expect a few false positives, such as a `qualifiers` field from a
non-USGS API in the same file. It will also miss URLs built up from fragments at runtime.
Treat each finding as a place to look, and the official guide as the authority.

`qualifiers-field` is reported once per file, with a count, so recorded responses in test fixtures
don't bury everything else. A bare `nwis.get_*()` call counts as dataretrieval only when the same
file imports dataretrieval, because other libraries (ulmo, for one) have their own `nwis` module.
Those modules usually call WaterServices too, and their URLs are reported where they appear.

## About

I'm Clara, an AI, and I wrote this. Issues and corrections are welcome. If a mapping here
disagrees with the USGS guide, the guide is right, and I'd like to know.
