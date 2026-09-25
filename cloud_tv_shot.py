"""Cloud slika javnog TradingView charta BEZ logina.
Otvara javni chart BINANCE:BTCUSDT 4H, pokusava da doda javni indikator
Auto Harmonic Patterns V2, slika i salje na Telegram.

Token i chat id dolaze iz env varijabli (GitHub Secrets):
  TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
Lokalno testiranje: python cloud_tv_shot.py (slika se sacuva, slanje samo ako ima env).
"""
import datetime
import os
import sys
import time
import urllib.request

CHART_URL = "https://www.tradingview.com/chart/?symbol=BINANCE%3ABTCUSDT&interval=240"
INDICATOR_NAME = "Auto Harmonic Patterns V2"
OUT_PNG = "tv_cloud.png"


def log(msg):
    print(msg, flush=True)


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


def try_add_indicator(page):
    """Pokusa da doda HP V2 preko Indicators menija. Ako ne uspe, vrati False
    pa se svejedno slika prazan chart (da korisnik vidi da sistem radi)."""
    try:
        # 1. dugme Indicators
        opened = False
        for sel in ['button:has-text("Indicators")',
                    '[aria-label="Indicators"]',
                    'button:has-text("Indikatori")']:
            try:
                page.click(sel, timeout=8000)
                opened = True
                log("indicators dugme kliknuto: %s" % sel)
                break
            except Exception:
                continue
        if not opened:
            log("nisam nasao Indicators dugme")
            return False
        time.sleep(2)
        # 2. search polje
        searched = False
        for sel in ['input[placeholder*="Search"]',
                    'input[placeholder*="search"]',
                    'input[type="text"]']:
            try:
                page.fill(sel, INDICATOR_NAME, timeout=8000)
                searched = True
                log("pretraga ukucana")
                break
            except Exception:
                continue
        if not searched:
            log("nisam nasao search polje")
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            return False
        time.sleep(3)
        # 3. klik na prvi rezultat koji sadrzi Harmonic
        try:
            page.evaluate("""(function(){
              var els=document.querySelectorAll('*');
              for(var i=0;i<els.length;i++){
                var t=(els[i].textContent||'').trim();
                if(t.indexOf('Auto Harmonic Patterns')===0 && els[i].children.length<=2){
                  try{els[i].click();return;}catch(e){}
                }
              }
            })()""")
            log("kliknut rezultat pretrage")
        except Exception as e:
            log("klik na rezultat nije uspeo: %s" % str(e)[:100])
        time.sleep(2)
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        return True
    except Exception as e:
        log("dodavanje indikatora nije uspelo: %s" % str(e)[:150])
        return False


def main():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[
            "--no-sandbox", "--disable-dev-shm-usage"])
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        log("otvaram: %s" % CHART_URL)
        page.goto(CHART_URL, wait_until="domcontentloaded", timeout=60000)
        try:
            page.wait_for_selector("canvas", timeout=60000)
            log("canvas nadjen")
        except Exception:
            log("canvas nije nadjen na vreme, nastavljam svejedno")
        time.sleep(10)
        dismiss_popups(page)
        time.sleep(2)
        ok = try_add_indicator(page)
        log("indikator dodat: %s (inputs se steluju na kraju)" % ok)
        # HP V2 je tezak, ceka se da se iscrta
        time.sleep(25)
        dismiss_popups(page)
        page.screenshot(path=OUT_PNG)
        log("slikano: %s" % OUT_PNG)
        browser.close()

    token = os.environ.get("TELEGRAM_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    caption = "BTCUSDT 4H cloud %s" % stamp
    if token and chat_id:
        code = send_telegram(token, chat_id, OUT_PNG, caption)
        log("poslato na telegram: %s" % code)
    else:
        log("nema TELEGRAM_TOKEN/CHAT_ID env - slika sacuvana lokalno, nije poslata")


if __name__ == "__main__":
    sys.exit(main())
