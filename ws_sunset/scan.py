"""Find code that will break when USGS WaterServices is decommissioned (Q1 2027).

Every mapping below comes from the USGS migration guide
(https://api.waterdata.usgs.gov/docs/ogcapi/migration/) and decommission notice
(https://waterdata.usgs.gov/blog/api-waterservices-decom/). This tool only points;
it never rewrites code, and a finding is a place to look, not a verdict.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass

GUIDE = "https://api.waterdata.usgs.gov/docs/ogcapi/migration/"
OGC = "https://api.waterdata.usgs.gov/ogcapi/v1/collections/"

# legacy endpoint -> (replacement, guide section, note)
ENDPOINTS = {
    "iv": (OGC + "continuous  (latest values: " + OGC + "latest-continuous)",
           "#migrating-from-%2Fiv-to-%2Fcontinuous",
           "one feature per observation, not grouped per time series; at most 3 years per query"),
    "dv": (OGC + "daily", "#migrating-from-%2Fdv-to-%2Fdaily", ""),
    "site": (OGC + "monitoring-locations  (period of record: " + OGC + "time-series-metadata)",
             "#migrating-from-%2Fsite-to-%2Fmonitoring-locations", ""),
    "gwlevels": (OGC + "field-measurements", "#migrating-from-%2Fgwlevels-to-%2Ffield-measurements", ""),
    "measurements": (OGC + "field-measurements  (channel: " + OGC + "channel-measurements)",
                     "#migrating-from-%2Fmeasurements-to-%2Ffield-measurements", ""),
    "peak": (OGC + "peaks", "#migrating-from-%2Fpeak-to-%2Fpeaks", ""),
    "stat": ("the modernized statistics API", "", "see the statistics API documentation"),
    "qwdata": ("the samples-data API", "", "see the samples-data API documentation"),
}

LEGACY_URL = re.compile(
    r"(?:waterservices\.usgs\.gov|waterdata\.usgs\.gov)/nwis/(iv|dv|site|gwlevels|measurements|peak|stat|qwdata)\b",
    re.I)
ANY_WATERSERVICES = re.compile(r"waterservices\.usgs\.gov", re.I)
R_READNWIS = re.compile(r"\b(readNWIS\w*|whatNWIS\w*)\s*\(")
PY_NWIS = re.compile(r"(\bfrom\s+dataretrieval\s+import\s+[^\n]*\bnwis\b|\bimport\s+dataretrieval\.nwis\b|\bdataretrieval\.nwis\b|\bnwis\.(get_\w+|what_\w+)\s*\()")
# provisional checks written against the legacy qualifiers list / *_cd columns
QUAL_P = re.compile(r"""(['"])P\1\s+(?:not\s+)?in\s+[\w.\[\]'"]*qualifiers|qualifiers[\w.\[\]'"]*\s*(?:==|!=|\.includes\(|\.contains\(|%in%)\s*\(?\s*(['"])P\2""")
# reading the legacy qualifiers field at all (only reported in files that also use WaterServices)
QUAL_FIELD = re.compile(r"""['"]qualifiers['"]|\.qualifiers\b""")
CD_COLUMN = re.compile(r"""['"`]?\w*_\d{5}_cd['"`]?""")

EXTS = {".py", ".r", ".rmd", ".qmd", ".ipynb", ".js", ".mjs", ".ts", ".tsx", ".jsx", ".sh", ".rb", ".go",
        ".java", ".cs", ".php", ".jl", ".m", ".sql", ".yml", ".yaml", ".toml", ".cfg", ".ini", ".md", ".html"}
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".tox", "renv"}


@dataclass
class Finding:
    path: str
    line: int
    kind: str
    match: str
    replacement: str
    note: str
    guide: str


def scan_text(path: str, text: str) -> list[Finding]:
    out: list[Finding] = []
    for i, line in enumerate(text.splitlines(), 1):
        seen_url = False
        for m in LEGACY_URL.finditer(line):
            seen_url = True
            rep, anchor, note = ENDPOINTS[m.group(1).lower()]
            out.append(Finding(path, i, "legacy-endpoint", m.group(0), rep, note, GUIDE + anchor))
        if not seen_url and ANY_WATERSERVICES.search(line):
            out.append(Finding(path, i, "legacy-host", ANY_WATERSERVICES.search(line).group(0),
                               "api.waterdata.usgs.gov/ogcapi/v1", "waterservices.usgs.gov is being decommissioned", GUIDE))
        for m in R_READNWIS.finditer(line):
            out.append(Finding(path, i, "r-dataRetrieval", m.group(1),
                               "the read_waterdata() family in current dataRetrieval",
                               "readNWIS functions call WaterServices", "https://doi-usgs.github.io/dataRetrieval/"))
        m = PY_NWIS.search(line)
        if m:
            out.append(Finding(path, i, "py-dataretrieval", m.group(0).strip(),
                               "the dataretrieval.waterdata module",
                               "the nwis module calls WaterServices", "https://github.com/DOI-USGS/dataretrieval-python"))
        m = QUAL_P.search(line)
        if m:
            out.append(Finding(path, i, "provisional-check", m.group(0),
                               "approval_status == 'Provisional'",
                               "approval status moved out of qualifiers into approval_status; a null or "
                               "missing qualifier does not mean approved", GUIDE + "#migrating-from-%2Fiv-to-%2Fcontinuous"))
        m = CD_COLUMN.search(line)
        if m:
            out.append(Finding(path, i, "rdb-cd-column", m.group(0),
                               "approval_status (P/A) plus qualifier (all other codes)",
                               "RDB *_cd columns are split into two fields", GUIDE + "#migrating-from-%2Fiv-to-%2Fcontinuous"))
    if any(f.kind in ("legacy-endpoint", "legacy-host", "r-dataRetrieval", "py-dataretrieval") for f in out):
        flagged = {f.line for f in out if f.kind == "provisional-check"}
        for i, line in enumerate(text.splitlines(), 1):
            m = QUAL_FIELD.search(line)
            if m and i not in flagged:
                out.append(Finding(path, i, "qualifiers-field", m.group(0),
                                   "approval_status (Approved/Provisional) and qualifier (other codes)",
                                   "the legacy qualifiers list is split in the new API; anything stored or "
                                   "displayed from it needs both fields", GUIDE + "#migrating-from-%2Fiv-to-%2Fcontinuous"))
    out.sort(key=lambda f: f.line)
    return out


def read_source(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read(4_000_000)
    except OSError:
        return None
    if path.lower().endswith(".ipynb"):
        try:
            nb = json.loads(text)
            return "\n".join("".join(c.get("source", [])) for c in nb.get("cells", []))
        except (ValueError, AttributeError):
            return text
    return text


def iter_files(roots: list[str]):
    for root in roots:
        if os.path.isfile(root):
            yield root
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for f in filenames:
                if os.path.splitext(f)[1].lower() in EXTS:
                    yield os.path.join(dirpath, f)


def scan(roots: list[str]) -> list[Finding]:
    found: list[Finding] = []
    for path in iter_files(roots):
        text = read_source(path)
        if text is not None:
            found += scan_text(path, text)
    return found


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ws-sunset", description=__doc__.splitlines()[0])
    ap.add_argument("paths", nargs="*", default=["."])
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)
    found = scan(args.paths)
    if args.json:
        print(json.dumps([asdict(f) for f in found], indent=1))
    else:
        for f in found:
            print(f"{f.path}:{f.line}: [{f.kind}] {f.match}\n    -> {f.replacement}"
                  + (f"\n    note: {f.note}" if f.note else "") + f"\n    guide: {f.guide}")
        kinds = sorted({f.kind for f in found})
        print(f"\n{len(found)} finding(s) in {len({f.path for f in found})} file(s)" + (f": {', '.join(kinds)}" if kinds else ""))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
