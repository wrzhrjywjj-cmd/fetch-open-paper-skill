#!/usr/bin/env python3
import argparse
import hashlib
import io
import re
import sys
import tarfile
import time
import unicodedata
import urllib.error
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path


FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024
TRANSIENT_HTTP = {408, 425, 429, 500, 502, 503, 504}
STOPWORDS = {
    "a", "an", "and", "as", "at", "by", "for", "from", "in", "of", "on", "or",
    "the", "to", "with",
}


class PaperDownloadError(Exception):
    def __init__(self, category: str, message: str):
        super().__init__(message)
        self.category = category


def safe_title(title: str, max_length: int = 180) -> str:
    name = FORBIDDEN.sub("_", " ".join(title.split())).rstrip(" .")
    if not name:
        name = "paper"
    if name.upper() in RESERVED:
        name = f"_{name}"
    return name[:max_length].rstrip(" .") or "paper"


def unique_path(directory: Path, stem: str, content: bytes) -> Path:
    candidate = directory / f"{stem}.pdf"
    if not candidate.exists():
        return candidate
    digest = hashlib.sha256(content).digest()
    if hashlib.sha256(candidate.read_bytes()).digest() == digest:
        return candidate
    index = 2
    while True:
        candidate = directory / f"{stem} ({index}).pdf"
        if not candidate.exists():
            return candidate
        if hashlib.sha256(candidate.read_bytes()).digest() == digest:
            return candidate
        index += 1


def normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value or "")
    unaccented = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join("".join(char.casefold() if char.isalnum() else " " for char in unaccented).split())


def title_terms(value: str):
    terms = [term for term in normalize(value).split() if len(term) > 1 and term not in STOPWORDS]
    return list(dict.fromkeys(terms))


def pair_title_score(expected: str, candidate: str) -> float:
    left = normalize(expected)
    right = normalize(candidate)
    if not left or not right:
        return 0.0
    if left in right and len(left) / len(right) >= 0.65:
        return 1.0
    if right in left and len(right) / len(left) >= 0.90:
        return 1.0
    ratio = SequenceMatcher(None, left, right).ratio()
    terms = title_terms(expected)
    if terms:
        candidate_terms = set(right.split())
        denominator = sum(len(term) for term in terms)
        coverage = sum(len(term) for term in terms if term in candidate_terms) / denominator
    else:
        coverage = 0.0
    return max(ratio, coverage * 0.92)


def best_title_score(expected: str, metadata_title: str, page_texts, authors) -> float:
    scores = []
    if metadata_title:
        scores.append(pair_title_score(expected, metadata_title))

    expected_authors = author_tokens(authors)
    for page_text in page_texts[:2]:
        lines = [" ".join(line.split()) for line in page_text.splitlines() if line.strip()][:60]
        author_line = None
        for index, line in enumerate(lines):
            if expected_authors.intersection(normalize(line).split()):
                author_line = index
                break
        if author_line is not None and author_line >= 2:
            lines = lines[:author_line]
        else:
            lines = lines[:12]
        for start in range(len(lines)):
            for width in range(1, 7):
                group = " ".join(lines[start:start + width])
                if group:
                    scores.append(pair_title_score(expected, group))
    return max(scores, default=0.0)


def author_tokens(authors):
    candidates = set()
    for author in authors:
        for token in normalize(author).split():
            if len(token) >= 3:
                candidates.add(token)
    return candidates


def extract_and_verify(data: bytes, title: str, authors, min_title_score: float):
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise PaperDownloadError("missing-dependency", "pypdf is required for bibliographic verification.") from exc

    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                pass
        page_count = len(reader.pages)
        if page_count < 1:
            raise ValueError("PDF has no pages.")
        metadata = reader.metadata or {}
        metadata_title = str(metadata.get("/Title", "") or "")
        metadata_author = str(metadata.get("/Author", "") or "")
        page_texts = []
        for page in reader.pages[:5]:
            page_texts.append(page.extract_text() or "")
    except Exception as exc:
        raise PaperDownloadError("invalid-pdf", f"PDF parsing failed: {exc}") from exc

    score = best_title_score(title, metadata_title, page_texts, authors)
    if score < min_title_score:
        raise PaperDownloadError(
            "bibliographic-mismatch",
            f"title did not match (score={score:.3f}, required={min_title_score:.3f}).",
        )

    searchable = normalize("\n".join([metadata_author, *page_texts]))
    searchable_tokens = set(searchable.split())
    expected_authors = author_tokens(authors)
    matched_authors = sorted(expected_authors.intersection(searchable_tokens))
    if expected_authors and not matched_authors:
        raise PaperDownloadError(
            "bibliographic-mismatch",
            "none of the supplied author surnames appeared in PDF metadata or the first five pages.",
        )
    if not expected_authors:
        raise PaperDownloadError("missing-metadata", "supply at least one author surname with --author.")

    extracted_chars = sum(len(text.strip()) for text in page_texts)
    return {
        "pages": page_count,
        "title_score": score,
        "matched_authors": matched_authors,
        "extracted_chars": extracted_chars,
    }


def read_limited(stream) -> bytes:
    data = stream.read(MAX_DOWNLOAD_BYTES + 1)
    if len(data) > MAX_DOWNLOAD_BYTES:
        raise PaperDownloadError("file-too-large", "download exceeded the 100 MB safety limit.")
    return data


def fetch_url(url: str, attempts: int):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
        },
    )
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = read_limited(response)
                return data, response.geturl(), response.headers.get("Content-Type", "")
        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403}:
                raise PaperDownloadError(
                    "browser-fallback",
                    f"HTTP {exc.code} from direct request; retry the public page in a normal browser.",
                ) from exc
            if exc.code in {404, 410}:
                raise PaperDownloadError("link-not-found", f"HTTP {exc.code} from source.") from exc
            if exc.code in TRANSIENT_HTTP and attempt < attempts:
                delay = min(2 ** (attempt - 1), 8)
                retry_after = exc.headers.get("Retry-After", "") if exc.headers else ""
                if retry_after.isdigit():
                    delay = min(max(int(retry_after), 1), 10)
                time.sleep(delay)
                continue
            category = "network-error" if exc.code in TRANSIENT_HTTP else "http-error"
            raise PaperDownloadError(category, f"HTTP {exc.code} from source.") from exc
        except urllib.error.URLError as exc:
            if attempt < attempts:
                time.sleep(min(2 ** (attempt - 1), 8))
                continue
            raise PaperDownloadError("network-error", str(exc.reason)) from exc
    raise PaperDownloadError("network-error", "download attempts exhausted.")


def read_source(args):
    if args.file:
        path = Path(args.file)
        if not path.is_file():
            raise PaperDownloadError("file-not-found", f"local file does not exist: {path}")
        if path.stat().st_size > MAX_DOWNLOAD_BYTES:
            raise PaperDownloadError("file-too-large", "local file exceeded the 100 MB safety limit.")
        return path.read_bytes(), str(path.resolve()), "application/pdf"

    source_url = args.url or args.archive_url
    data, final_url, content_type = fetch_url(source_url, args.attempts)
    if args.archive_url:
        if not args.archive_member:
            raise PaperDownloadError("archive-error", "--archive-member is required with --archive-url.")
        try:
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
                matches = [
                    member for member in archive.getmembers()
                    if member.isfile() and Path(member.name).name == args.archive_member
                ]
                if len(matches) != 1:
                    raise PaperDownloadError(
                        "archive-error",
                        f"expected one archive member named {args.archive_member!r}; found {len(matches)}.",
                    )
                extracted = archive.extractfile(matches[0])
                if extracted is None:
                    raise PaperDownloadError("archive-error", "could not read the requested archive member.")
                data = read_limited(extracted)
        except PaperDownloadError:
            raise
        except Exception as exc:
            raise PaperDownloadError("archive-error", str(exc)) from exc
    return data, final_url, content_type


def main() -> int:
    parser = argparse.ArgumentParser(description="Download, identify, and save a public scholarly PDF.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url", help="Direct public PDF URL.")
    source.add_argument("--archive-url", help="Trusted public .tar.gz package URL.")
    source.add_argument("--file", help="Local PDF to verify, copy, and rename.")
    parser.add_argument("--archive-member", help="PDF member basename inside --archive-url.")
    parser.add_argument("--title", required=True, help="Canonical expected paper title.")
    parser.add_argument("--author", action="append", required=True, help="Expected author surname; repeat as needed.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--attempts", type=int, default=3, choices=range(1, 6))
    parser.add_argument("--min-title-score", type=float, default=0.80)
    args = parser.parse_args()

    data, final_source, content_type = read_source(args)
    if not data.startswith(b"%PDF-"):
        detail = f" content-type={content_type!r}" if content_type else ""
        category = "browser-fallback" if "html" in content_type.casefold() else "not-pdf"
        raise PaperDownloadError(
            category,
            f"content is missing the %PDF signature.{detail} source={final_source}",
        )
    if len(data) < 1024:
        raise PaperDownloadError("invalid-pdf", "PDF is unexpectedly small.")

    result = extract_and_verify(data, args.title, args.author, args.min_title_score)
    directory = Path(args.output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    resolved_directory = str(directory.resolve())
    max_stem = min(180, 230 - len(resolved_directory))
    if max_stem < 32:
        raise PaperDownloadError("path-too-long", "output directory is too deep for a safe Windows filename.")
    destination = unique_path(directory, safe_title(args.title, max_stem), data)
    if not destination.exists():
        destination.write_bytes(data)

    authors = ",".join(result["matched_authors"])
    print(
        f"VERIFIED pages={result['pages']} title_score={result['title_score']:.3f} "
        f"author_match={authors} source={final_source}"
    )
    print(destination.resolve())
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PaperDownloadError as exc:
        print(f"ERROR [{exc.category}]: {exc}", file=sys.stderr)
        raise SystemExit(1)
    except Exception as exc:
        print(f"ERROR [unexpected]: {exc}", file=sys.stderr)
        raise SystemExit(1)
