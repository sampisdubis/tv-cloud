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
import re
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


def login_state(page):
    """Vraca (ima_sign_in_link, ima_user_meni) sa naslovne strane."""
    try:
        return page.evaluate("""(function(){
          var signLink = document.querySelector('a[href*="accounts/signin"]') !== null;
          var um = document.querySelectorAll('button');
          var userMenu = false;
          for (var i=0;i<um.length;i++){
            var a=(um[i].getAttribute('aria-label')||'');
            if(/user menu|account|profile/i.test(a)){ userMenu = true; break; }
          }
          return [signLink, userMenu];
        })()""")
    except Exception:
        return [None, None]


def layout_blocked_text(page):
    try:
        txt = page.evaluate("document.body ? document.body.innerText.slice(0,3000) : ''")
    except Exception:
        return ""
    return txt


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
        # 1. prvo naslovna strana da sesija legne, pa provera prijave
        log("otvaram naslovnu za proveru prijave")
        page.goto("https://www.tradingview.com/", wait_until="domcontentloaded", timeout=60000)
        time.sleep(6)
        sign_link, user_menu = login_state(page)
        logged_in = (user_menu is True) or (sign_link is False)
        log("prijava prepoznata: %s (sign_link=%s user_menu=%s)" % (logged_in, sign_link, user_menu))
        if not logged_in:
            log("KOLACIC NE VALJA: nisi ulogovan ni na naslovnoj")
            if token and chat_id:
                send_text(token, chat_id,
                          "TV cloud: kolacic ne valja (prijava nije prosla). "
                          "Izvadi nova 2 kljuca iz browsera i zameni tajne sifre.")
                log("poslato upozorenje na telegram")
            browser.close()
            return 0
        # 2. isti sacuvani layout, 3 vremenska okvira - ista HP V2 podesavanja
        shots = [("4H", "240", "tv_cloud_4H.png"),
                 ("1H", "60", "tv_cloud_1H.png"),
                 ("15m", "15", "tv_cloud_15m.png")]
        ok_map = {}
        for tf_name, tf_val, out in shots:
            url = re.sub(r"([?&])interval=\d+", r"\g<1>interval=" + tf_val, LAYOUT_URL)
            if "interval=" not in url:
                url += ("&" if "?" in url else "?") + "interval=" + tf_val
            log("TF %s: otvaram" % tf_name)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
            except Exception as e:
                log("TF %s: goto greska: %s" % (tf_name, str(e)[:100]))
                ok_map[tf_name] = False
                continue
            canvas_ok = True
            try:
                page.wait_for_selector("canvas", timeout=60000)
            except Exception:
                canvas_ok = False
            time.sleep(8)
            dismiss_popups(page)
            time.sleep(2)
            body = layout_blocked_text(page)
            blocked = "Can't open this chart layout" in body
            if (blocked or not canvas_ok):
                log("TF %s: problem (blocked=%s canvas_ok=%s) - jedan reload" % (tf_name, blocked, canvas_ok))
                try:
                    page.reload(wait_until="domcontentloaded", timeout=60000)
                except Exception:
                    pass
                time.sleep(10)
                dismiss_popups(page)
                try:
                    page.wait_for_selector("canvas", timeout=60)
                    canvas_ok = True
                except Exception:
                    canvas_ok = False
                blocked = "Can't open this chart layout" in layout_blocked_text(page)
            if blocked or not canvas_ok:
                log("TF %s: NIJE USPEO (blocked=%s canvas_ok=%s)" % (tf_name, blocked, canvas_ok))
                ok_map[tf_name] = False
                continue
            # HP V2 je tezak, ceka se da se iscrta
            time.sleep(20)
            dismiss_popups(page)
            page.screenshot(path=out)
            log("TF %s: slikano: %s" % (tf_name, out))
            ok_map[tf_name] = True
        browser.close()

    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if token and chat_id:
        for tf_name, tf_val, out in shots:
            if ok_map.get(tf_name):
                code = send_telegram(token, chat_id, out, "BTCUSDT %s cloud %s" % (tf_name, stamp))
                log("TF %s: poslato na telegram: %s" % (tf_name, code))
        failed = [tf for tf, _, _ in shots if not ok_map.get(tf)]
        if failed:
            send_text(token, chat_id, "TV cloud: nisu se ucitali: %s" % ", ".join(failed))
            log("poslato upozorenje za: %s" % ", ".join(failed))
    else:
        log("nema TELEGRAM_TOKEN/CHAT_ID env - slike sacuvane lokalno, nisu poslate")


if __name__ == "__main__":
    sys.exit(main())
