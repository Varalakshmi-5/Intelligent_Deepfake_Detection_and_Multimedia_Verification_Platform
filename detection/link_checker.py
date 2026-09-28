"""
Rule-based URL safety analysis - purely lexical/structural, no network
fetch (avoids SSRF risk entirely; never visits the actual URL).
"""
import re
from urllib.parse import urlparse

SUSPICIOUS_TLDS = {
    "tk", "ml", "ga", "cf", "gq", "xyz", "top", "click", "work", "live",
    "fit", "loan", "men", "date", "review", "download", "stream",
}

URL_SHORTENERS = {
    "bit.ly", "tinyurl.com", "goo.gl", "t.co", "ow.ly", "is.gd",
    "buff.ly", "adf.ly", "shorte.st", "rebrand.ly",
}

# brand name -> its legitimate real domain(s). A URL "impersonates" a
# brand if the brand name appears in the HOST but the host isn't
# actually the brand's real domain (or a subdomain of it).
KNOWN_BRAND_DOMAINS = {
    "paypal": ["paypal.com"],
    "amazon": ["amazon.com", "amazon.in", "amazon.co.uk", "amazon.de"],
    "google": ["google.com", "gmail.com"],
    "microsoft": ["microsoft.com", "live.com", "outlook.com"],
    "apple": ["apple.com", "icloud.com"],
    "netflix": ["netflix.com"],
    "facebook": ["facebook.com", "fb.com"],
    "instagram": ["instagram.com"],
    "whatsapp": ["whatsapp.com"],
    "chase": ["chase.com"],
    "wellsfargo": ["wellsfargo.com"],
    "hdfcbank": ["hdfcbank.com"],
    "icicibank": ["icicibank.com"],
}

SUSPICIOUS_KEYWORDS = ["login", "verify", "secure", "account", "update", "confirm", "signin", "password", "banking"]


def _host_matches_domain(host, domain):
    return host == domain or host.endswith("." + domain)


def analyze_url(raw_url):
    flags = []
    points = 0

    url = raw_url.strip()
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "http://" + url

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    full_lower = url.lower()
    host_normalized = host.replace("-", "").replace("_", "")

    # 1. No HTTPS
    if parsed.scheme != "https":
        flags.append("Connection is not encrypted (no HTTPS)")
        points += 1

    # 2. Raw IP address as host
    if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", host):
        flags.append("URL uses a raw IP address instead of a domain name")
        points += 3

    # 3. '@' trick (https://real-site.com@evil.com/)
    if "@" in url.split("://", 1)[-1].split("/")[0]:
        flags.append("URL contains an '@' symbol before the domain (classic redirect trick)")
        points += 4

    # 4. Punycode / homograph domains
    if "xn--" in host:
        flags.append("Domain uses punycode encoding (possible lookalike/homograph attack)")
        points += 3

    # 5. Excessive subdomains
    if host.count(".") >= 4:
        flags.append("Unusually many subdomains in the URL")
        points += 2

    # 6. Suspicious TLD
    tld = host.rsplit(".", 1)[-1] if "." in host else ""
    if tld in SUSPICIOUS_TLDS:
        flags.append(f"Domain uses a TLD commonly associated with spam/phishing (.{tld})")
        points += 1

    # 7. URL shortener
    if host in URL_SHORTENERS:
        flags.append(f"URL uses a link shortener ({host}) - the real destination is hidden")
        points += 2

    # 8. Brand impersonation: brand name appears in the HOST but the
    # host isn't actually that brand's real domain.
    for brand, real_domains in KNOWN_BRAND_DOMAINS.items():
        if brand in host_normalized and not any(_host_matches_domain(host, d) for d in real_domains):
            flags.append(f"Domain contains '{brand}' but is not {brand}'s real website")
            points += 4
            break
    else:
        # brand mentioned only in path/query (not the host) — much weaker signal
        for brand, real_domains in KNOWN_BRAND_DOMAINS.items():
            if brand in full_lower and not any(_host_matches_domain(host, d) for d in real_domains):
                flags.append(f"Mentions '{brand}' but the domain is not {brand}'s real website")
                points += 2
                break

    # 9. Suspicious keywords + already-flagged URL
    keyword_hits = [kw for kw in SUSPICIOUS_KEYWORDS if kw in full_lower]
    if keyword_hits and points > 0:
        flags.append(f"Contains sensitive-sounding keywords ({', '.join(keyword_hits[:3])}) alongside other red flags")
        points += 1

    # 10. Excessively long URL
    if len(url) > 120:
        flags.append("URL is unusually long, which can be used to obscure the real destination")
        points += 1

    if points >= 6:
        tier = "HIGH"
        verdict = "Likely Unsafe"
    elif points >= 3:
        tier = "MEDIUM"
        verdict = "Some Risk Indicators"
    else:
        tier = "LOW"
        verdict = "No Significant Risk Indicators"

    if not flags:
        flags.append("No suspicious patterns detected in this URL")

    return {"risk_tier": tier, "verdict": verdict, "risk_points": points, "flags": flags, "host": host}
