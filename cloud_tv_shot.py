"""Cloud slika TV charta SA prijavom (kolacici).
Otvara TVOJ sacuvani layout (vec ima HP V2 sa tvojim inputs podesavanjima),
saceka da se iscrta, slika i salje na Telegram.

Secrets (GitHub -> Settings -> Secrets -> Actions):
  TELEGRAM_TOKEN, TELEGRAM_CHAT_ID - bot za slanje
  TV_SESSIONID, TV_SESSIONID_SIGN - kolacici sa tvog browsera (tvoja prijava)
  LAYOUT_URL (opciono) - link tvog charta

Vazno: vrednosti kolacica se nikad ne salju u chat, samo se nalepe u Secrets.
"""
import datetime
import os
import sys
import time
import urllib.parse
import urllib.request

LAYOUT_URL = (os.environ.get("LAYOUT_URL", "").strip()
              or "https://www.tradingview.com/chart/LbQ2BN3G/?symbol=BINANCE%3ABTCUSDT&interval=240")
OUT_PNG = "tv_cloud.png"


def log(msg):
    print(msg, flush=True)


def send_text(token, chat_id, text):
    url = "https://api.telegram.org/bot%s/sendMessage" % token
    data = urllib.parse.urlencode(
        {"chat_id": chat_id, "text": text[:900]}).encode("utf-8")
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status


def send_telegram(token, chat_id, photo_path, caption):
    url = "https://api.telegram.org/bot%s/sendPhoto" % token
    boundary = "----tvcloud1234"
    with open(photo_path, "rb") as f:
        data = f.read()
    fields = {"chat_id": chat_id, "caption": caption[:900]}
    body = b""
    for k, v in fields.items():
        body += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                 % (boundary, k, v)).encode("utf-8", "replace")
    body += ("--%s\r\nContent-Disposition: form-data; name=\"photo\"; "
             "filename=\"chart.png\"\r\nContent-Type: image/png\r\n\r\n"
             % boundary).encode() + data + ("\r\n--%s--\r\n" % boundary).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "multipart/form-data; boundary=%s" % boundary})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status


def dismiss_popups(page):
    """Ugasi cookie i reklame da ne prekrivaju chart. Ne dira chart."""
    try:
        page.evaluate("""(function(){
          var texts = ['Accept all','Accept','I agree','Got it','OK'];
          var btns = document.querySelectorAll('button');
          for (var i=0;i<btns.length;i++){
            var t=(btns[i].textContent||'').trim();
            if (texts.indexOf(t)>=0){
              var r=btns[i].getBoundingClientRect();
              if (r.width>20 && r.width<300 && r.height>10 && r.height<80){
                try{btns[i].click();}catch(e){}
              }
            }
          }
        })()""")
    except Exception as e:
        log("popup dismiss preskocen: %s" % str(e)[:100])


def is_login_wall(page):
    """Proveri da li nas je TradingView bacio na prijavu (kolacic istekao)."""
    try:
        url = page.url
        if "/accounts/signin" in url or "login" in url.split("?")[0]:
            return True
        txt = page.evaluate("document.body ? document.body.innerText.slice(0,2000) : ''")
        if "Sign in" in txt and "Password" in txt and "TradingView" in txt:
            return True
    except Exception:
        pass
    return False


def main():
    from playwright.sync_api import sync_playwright

    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    sid = os.environ.get("TV_SESSIONID", "").strip()
    sign = os.environ.get("TV_SESSIONID_SIGN", "").strip()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[
            "--no-sandbox", "--disable-dev-shm-usage"])
        ctx = browser.new_context(viewport={"width": 1280, "height": 720})
        cookies = []
        if sid:
            cookies.append({"name": "sessionid", "value": sid,
                            "domain": ".tradingview.com", "path": "/"})
        if sign:
            cookies.append({"name": "sessionid_sign", "value": sign,
                            "domain": ".tradingview.com", "path": "/"})
        if cookies:
            ctx.add_cookies(cookies)
            log("kolacici ucitani: %d" % len(cookies))
        else:
            log("NEMA kolacica - bez prijave HP V2 ne moze na chart")
        page = ctx.new_page()
        log("otvaram tvoj layout")
        page.goto(LAYOUT_URL, wait_until="domcontentloaded", timeout=60000)
        try:
            page.wait_for_selector("canvas", timeout=60000)
            log("canvas nadjen")
        except Exception:
            log("canvas nije nadjen na vreme, nastavljam svejedno")
        time.sleep(10)
        dismiss_popups(page)
        time.sleep(2)

        if is_login_wall(page):
            log("LOGIN ZID: kolacic istekao ili ne valja")
            if token and chat_id:
                send_text(token, chat_id,
                          "TV cloud: prijava istekla, treba novi kolacic. "
                          "Slike pauzirane dok se ne ubaci novi.")
                log("poslato upozorenje na telegram")
            browser.close()
            return 0

        try:
            legend = page.evaluate(
                """(function(){
                  var legs=document.querySelectorAll('[data-name="legend"]');
                  var t=''; for(var i=0;i<legs.length;i++){ t+=legs[i].innerText+' '; }
                  return t.slice(0,200);
                })()""")
            log("legenda: %s" % (legend or "prazna"))
        except Exception:
            pass
        # HP V2 je tezak, ceka se da se iscrta
        time.sleep(25)
        dismiss_popups(page)
        page.screenshot(path=OUT_PNG)
        log("slikano: %s" % OUT_PNG)
        browser.close()

    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    caption = "BTCUSDT 4H cloud %s" % stamp
    if token and chat_id:
        code = send_telegram(token, chat_id, OUT_PNG, caption)
        log("poslato na telegram: %s" % code)
    else:
        log("nema TELEGRAM_TOKEN/CHAT_ID env - slika sacuvana lokalno, nije poslata")


if __name__ == "__main__":
    sys.exit(main())
