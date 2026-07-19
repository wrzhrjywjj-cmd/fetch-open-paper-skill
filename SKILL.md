---
name: fetch-open-paper
description: Find, batch-retrieve, verify, and organize lawfully public scholarly-paper PDFs from titles, citations, DOIs, PMIDs, or arXiv identifiers. Ask once per task for an outputs subfolder when none is established, reuse it for later papers, accept any lawful public version, fall back to a normal browser when direct requests fail, verify title and author identity before saving, maintain a resumable CSV manifest, and report results. Use whenever the user asks to locate, retrieve, download, or verify scholarly papers or supplies paper identifiers or citation lists.
---

# Fetch Open Paper

Retrieve lawful public copies of requested papers and save verified PDFs in a user-named folder under the current task's `outputs` directory.

## Workflow

1. Check whether an output folder is established in the current task. If none exists, ask once for its name and wait. Reuse it for all later papers in the task; change it only when the user explicitly requests another folder.
2. Accept one Windows folder name, not an absolute or nested path. Reject empty names, `.` or `..`, separators, forbidden characters, and reserved device names. Set the destination to `outputs\\<folder-name>` and do not add another hidden directory level.
3. Create the destination once the folder is established. For a batch, initialize and maintain `下载结果.csv` with `scripts/update_manifest.py` before searching so interrupted work can resume. Skip an item already marked `已验证下载` only when its local PDF still passes validation.
4. Parse each DOI, title, PMID, arXiv ID, or citation. Normalize DOI URL prefixes. When a citation title is abbreviated or truncated, resolve authoritative metadata from the DOI or identifier before searching.
5. Record the canonical title, DOI when available, and at least one author surname. Deduplicate batch entries by normalized DOI, otherwise by normalized title.
6. Build a candidate queue rather than stopping after the first URL. Search current public sources in this order:
   - an official publisher open-access PDF or landing page;
   - PubMed Central, Europe PMC, arXiv, HAL, SSRN, Zenodo, or another trusted subject repository;
   - a university or institutional repository;
   - an author homepage or clearly authorized project site.
   Use Crossref, OpenAlex, Unpaywall, and publisher metadata to discover and confirm candidates. Prefer current HTTPS URLs. Treat DOI, handle, repository, and article pages as landing pages until a PDF response is confirmed.
7. Accept the version of record, accepted manuscript, author manuscript, repository copy, or preprint. Prefer the version of record when equally accessible, but do not fail merely because only another lawful public version exists. Record the version type, using `公开版本（类型未确认）` when it cannot be determined.
8. Do not use Sci-Hub, shadow libraries, credential bypasses, paywall circumvention, leaked copies, or unclear re-upload sites.
9. Confirm a candidate page matches the request using title and author information before downloading. DOI, venue, and year are additional evidence, not substitutes for a conflicting title or author.
10. Build the PDF filename from the canonical title. Replace every Windows-forbidden filename character (`<`, `>`, `:`, `"`, `/`, `\\`, `|`, `?`, and `*`) and every control character with an underscore (`_`). Trim trailing periods and spaces.
11. Try direct download first with `scripts/download_pdf.py`, passing the canonical title and one or more author surnames. The script retries transient errors, parses the PDF, verifies title and author, and writes only verified content into the destination.
12. Do not interpret HTTP 401/403, an HTML response, a JavaScript redirect, or a landing page as evidence that no public PDF exists. Mark the attempt `需浏览器尝试`. When the Chrome control skill is available, read and use it to open the exact public or official page in a normal browser session and activate its public PDF or download control. Do not inspect cookies, local storage, passwords, or session data.
13. Use the browser only as an access surface, not to bypass controls. Do not defeat CAPTCHA, login, license acceptance, subscription controls, or paywalls. If ordinary authentication is required, ask the user to sign in in the selected browser and continue only after confirmation.
14. After a browser download, pass the known local file to `scripts/download_pdf.py --file`. Save and rename it in the destination only after title and author verification succeeds. Keep unverified browser files outside `outputs`.
15. If the PDF is scanned or has too little extractable text, do not label it verified solely because it opens. Accept it only when title and author are reliably present in embedded PDF metadata; otherwise mark it `需人工核验`.
16. Do not mark a paper `未完成下载` after one failed candidate. Exhaust the current lawful candidate queue and perform the browser fallback when it is available. Record whether direct and browser attempts were made.
17. After every attempt, update `下载结果.csv` with the title, authors, DOI, status, version type, local filename, source, candidate links, direct-download result, browser result, attempt count, and timestamp.
18. Report successes exactly as `论文名称 — 已验证下载`. For an uncompleted paper, list its name and the best available download or landing-page link. Also link the output folder and manifest.

## Commands

Use the bundled Python runtime when ordinary `python` is unavailable.

Download and verify a direct PDF:

```powershell
& <python> scripts/download_pdf.py --url <direct-pdf-url> --title <canonical-title> --author <surname> --output-dir 'outputs\\<folder-name>'
```

Verify a browser-downloaded or otherwise local file:

```powershell
& <python> scripts/download_pdf.py --file <local-pdf> --title <canonical-title> --author <surname> --output-dir 'outputs\\<folder-name>'
```

Update the resumable result manifest:

```powershell
& <python> scripts/update_manifest.py --output-dir 'outputs\\<folder-name>' --title <canonical-title> --authors <authors> --doi <doi> --status <status> --increment-attempt
```

Pass `--author` more than once when useful. Use author surnames rather than initials. Treat a DOI landing page as metadata and follow its public PDF link first.
