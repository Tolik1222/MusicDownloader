import urllib.request
import urllib.error
import ssl

url = "https://www.stb.ua/masterchef/ua/video-2/"

headers_basic = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'uk,ru;q=0.9,en;q=0.8',
}

headers_full = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'Accept-Language': 'uk-UA,uk;q=0.9,ru;q=0.8,en-US;q=0.7,en;q=0.6',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
}

print("--- Method 1: urllib basic headers ---")
try:
    req = urllib.request.Request(url, headers=headers_basic)
    with urllib.request.urlopen(req, timeout=10) as resp:
        print(f"Success! Status: {resp.status}, HTML length: {len(resp.read())}")
except Exception as e:
    print(f"Failed: {e}")

print("\n--- Method 2: urllib full browser headers ---")
try:
    req = urllib.request.Request(url, headers=headers_full)
    with urllib.request.urlopen(req, timeout=10) as resp:
        print(f"Success! Status: {resp.status}, HTML length: {len(resp.read())}")
except Exception as e:
    print(f"Failed: {e}")

# Check if httpx is installed
try:
    import httpx
    print("\n--- Method 3: httpx with basic headers ---")
    try:
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            resp = client.get(url, headers=headers_basic)
            print(f"Success! Status: {resp.status_code}, HTML length: {len(resp.content)}")
    except Exception as e:
        print(f"Failed: {e}")

    print("\n--- Method 4: httpx with full browser headers ---")
    try:
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            resp = client.get(url, headers=headers_full)
            print(f"Success! Status: {resp.status_code}, HTML length: {len(resp.content)}")
    except Exception as e:
        print(f"Failed: {e}")
except ImportError:
    print("\nhttpx is not installed, skipping httpx tests.")
