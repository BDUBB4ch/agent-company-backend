"""Chat lock during renders (Barry, 2026-08-29: "chats should be locked
during this time and when im generating").

Appends one shared guard block to every deck + the classic dashboard:
polls /api/generate/status; while busy (image queue OR the video render
flag) it disables every known composer, shows a GENERATING banner, and a
fetch-guard blocks any POST /api/chat that slips through. Unlocks itself.

Idempotent (marker check), temp+rename writes, per-file verification.
"""
import os
import re

DASH = r"C:\Users\Owner\Desktop\AgentDashboard"
FILES = ["index.html", "neo.html", "neo-v4.html", "neo-roll6.html",
         "neo-holo.html", "neo-chamber.html", "neo-chamber-v1.html"]
MARKER = "render-chat-lock-2026-08-29"

BLOCK = """
<script>/* render-chat-lock-2026-08-29: chat locks while the GPU renders */
(function(){
  var API='http://127.0.0.1:8420';
  var SEL=['#chat-input','#send-btn','#con-input','#con-send','#b-send',
           '#pchat-input','#pchat-send','#cmd-input','#cmd-send'];
  var locked=false, banner=null;
  function ensureBanner(){
    if(banner) return banner;
    banner=document.createElement('div');
    banner.style.cssText='position:fixed;top:8px;left:50%;transform:translateX(-50%);'+
      'z-index:2147483000;background:#1a0f00;color:#ffb347;border:1px solid #ffb347;'+
      'padding:8px 18px;font:600 13px monospace;border-radius:6px;display:none;'+
      'box-shadow:0 0 18px rgba(255,140,0,.35);letter-spacing:1px';
    banner.textContent='\\ud83c\\udfac GENERATING \\u2014 chat is locked until the render finishes';
    document.body.appendChild(banner);
    return banner;
  }
  function apply(on){
    if(on===locked) return;
    locked=on;
    ensureBanner().style.display=on?'block':'none';
    SEL.forEach(function(s){
      var el=document.querySelector(s);
      if(!el) return;
      if(on){ el.dataset.rlPrev=el.disabled?'1':'0'; el.disabled=true; el.style.opacity='0.4'; }
      else if(el.dataset.rlPrev!=='1'){ el.disabled=false; el.style.opacity=''; }
    });
  }
  var _fetch=window.fetch;
  window.fetch=function(url,opts){
    try{
      if(locked && typeof url==='string' && url.indexOf('/api/chat')!==-1 &&
         opts && (opts.method||'GET').toUpperCase()==='POST'){
        return Promise.resolve(new Response(
          JSON.stringify({error:'GPU is rendering \\u2014 chat is locked until it finishes.'}),
          {status:503,headers:{'Content-Type':'application/json'}}));
      }
    }catch(e){}
    return _fetch.apply(this,arguments);
  };
  function poll(){
    if(document.hidden) return;
    _fetch(API+'/api/generate/status').then(function(r){return r.json();})
      .then(function(s){ apply(!!(s.busy||s.video_render_holding_gpu)); })
      .catch(function(){ apply(false); });
  }
  setInterval(poll,8000); setTimeout(poll,1500);
})();
</script>
"""


def main():
    for name in FILES:
        path = os.path.join(DASH, name)
        html = open(path, encoding="utf-8", errors="replace").read()
        if MARKER in html:
            print(f"{name}: already patched, skipped")
            continue
        if "</body>" in html:
            new = html.replace("</body>", BLOCK + "\n</body>", 1)
        else:
            new = html + BLOCK
        assert MARKER in new and len(new) > len(html), f"{name}: patch did not land"
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(new)
        os.replace(tmp, path)
        back = open(path, encoding="utf-8", errors="replace").read()
        assert MARKER in back, f"{name}: verify-after-write failed"
        print(f"{name}: patched ({len(html)} -> {len(back)} chars)")


if __name__ == "__main__":
    main()
